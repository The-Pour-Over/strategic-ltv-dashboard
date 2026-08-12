#!/usr/bin/env python3
"""Ingest Nicole's synced dashboard decisions into the variation queue.

The hosted dashboard writes her approvals/edits to decisions-inbox.json at
the ROOT of the strategic-ltv-dashboard repo (via decisionSync.ts). This
script — run during the weekly refresh, after `git pull` in that repo —
applies them to variation_queue.json:

  - variation build/upload approvals -> status building/uploading, her edited
    hook + user_note stamped on the option (trigger variation_worker.sh next)
  - skips/rejects -> status skipped/rejected
  - test promote/park records -> printed for the operator (test execution is
    live on the page itself; these are just records)

Processed entries are moved to `processed` inside the inbox with a stamp, so
they never double-apply; commit+push the inbox afterwards.

Usage: python3 scripts/ingest_decisions.py [--inbox <path>]
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import resolve_data_dir

# the inbox lives at the ROOT of the strategic-ltv-dashboard repo; when this
# script runs from that repo's checkout the default just works
DEFAULT_INBOX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "decisions-inbox.json")

STATUS = {"build": "building", "upload": "uploading", "skip": "skipped", "reject": "rejected"}

ap = argparse.ArgumentParser()
ap.add_argument("--inbox", default=DEFAULT_INBOX)
ap.add_argument("--data", default=None, help="dir holding variation_queue.json (default: auto-detect)")
args = ap.parse_args()
QUEUE = os.path.join(resolve_data_dir(args.data), "variation_queue.json")

if not os.path.exists(args.inbox):
    print("no inbox file — nothing synced since last ingest")
    sys.exit(0)

inbox = json.load(open(args.inbox))
pending = inbox.get("decisions") or {}
if not pending:
    print("inbox empty")
    sys.exit(0)

q = json.load(open(QUEUE))
opts = {o["id"]: o for o in (q.get("batch") or []) + ((q.get("competitor") or {}).get("batch") or [])}

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
to_run = []
for key, rec in list(pending.items()):
    kind, _, ident = key.partition(":")
    if kind == "variation":
        opt = opts.get(ident)
        action = rec.get("action")
        if not opt or action not in STATUS:
            print(f"! {key}: unknown option or action — leaving in inbox")
            continue
        if rec.get("hook"):
            opt["hook"] = "“" + rec["hook"].strip().strip("“”\"") + "”"
        if rec.get("note"):
            opt["user_note"] = rec["note"].strip()
        opt["status"] = STATUS[action]
        opt[f"{action}_at"] = rec.get("at") or now
        if action in ("build", "upload"):
            to_run.append((ident, action))
        print(f"✓ {key}: {action}" + (" (with her edits)" if rec.get("hook") or rec.get("note") else ""))
    else:
        print(f"• {key}: {rec.get('action')} recorded — check the page/Meta state for tests")
    inbox.setdefault("processed", {})[key] = {**rec, "ingested_at": now}
    del pending[key]

json.dump(q, open(QUEUE, "w"), indent=2)
json.dump(inbox, open(args.inbox, "w"), indent=1)

if to_run:
    print("\nNow run the worker for each approval:")
    for ident, action in to_run:
        print(f"  bash scripts/variation_worker.sh {ident} {action}")
print("\nRemember: commit+push the updated inbox in the strategic repo so the page sees a clean slate.")
