#!/bin/bash
# variation_worker.sh <option_id> <build|upload>
# Spawned by the vite dev server when Nicole checks a variation on the Action
# Items page. Runs headless Claude (same pattern as Matt's daily refresh) to
# build the creative or upload it (paused) to Meta, then notifies her.
set -uo pipefail

ID="${1:?option id required}"
ACTION="${2:?action required}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="$REPO/.vari-logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%F_%H%M%S)_${ID}_${ACTION}.log"

# Prefer claude on PATH (Matt's pipeline installs the CLI); fall back to the
# newest VS Code extension bundle (Nicole's setup).
CLAUDE=$(command -v claude || ls -d "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude 2>/dev/null | sort -V | tail -1)
if [ -z "$CLAUDE" ]; then
  echo "claude binary not found" >> "$LOG"
  osascript -e 'display notification "Worker failed: Claude binary not found" with title "TPO Action Items"'
  exit 1
fi

PROMPT_FILE="$REPO/scripts/variation_${ACTION}_prompt.md"
if [ ! -f "$PROMPT_FILE" ]; then
  echo "prompt file missing: $PROMPT_FILE" >> "$LOG"
  exit 1
fi

# Uploads must run one at a time: concurrent uploads once raced and created
# duplicate ad set pairs (2026-07-24). mkdir is atomic — first worker wins,
# the rest wait their turn (up to ~15 min).
if [ "$ACTION" = "upload" ]; then
  LOCK_DIR="$LOGDIR/.upload-lock"
  waited=0
  until mkdir "$LOCK_DIR" 2>/dev/null; do
    sleep 10
    waited=$((waited + 10))
    if [ "$waited" -ge 900 ]; then
      echo "gave up waiting for upload lock" >> "$LOG"
      exit 1
    fi
  done
  trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT
fi

cd "$REPO"
{
  echo "=== $(date '+%F %T') worker start id=$ID action=$ACTION ==="
  "$CLAUDE" -p "$(cat "$PROMPT_FILE")

The TARGET option id is: $ID" --dangerously-skip-permissions
  RC=$?
  echo "=== $(date '+%F %T') worker done rc=$RC ==="
  # Safety net: if the session died without updating the queue, mark it failed
  python3 - "$ID" "$ACTION" <<'PYEOF'
import json, sys
oid, action = sys.argv[1], sys.argv[2]
p = 'client/public/data/variation_queue.json'
q = json.load(open(p))
opts = (q.get('batch') or []) + ((q.get('competitor') or {}).get('batch') or [])
for o in opts:
    if o['id'] == oid and o.get('status') in ('building', 'uploading'):
        o['status'] = f"{action}_failed"
        o['error'] = 'worker exited without completing — see .vari-logs'
        json.dump(q, open(p, 'w'), indent=2)
        import subprocess
        subprocess.run(['osascript', '-e',
            f'display notification "{action} failed for {oid} — check .vari-logs" with title "TPO Action Items"'])
        break
PYEOF
} >> "$LOG" 2>&1
