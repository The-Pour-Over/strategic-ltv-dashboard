# Producer scripts — action-center/data

The scripts that produce/consume the files in `action-center/data/` (same
schema as `client/public/data/` in the `ltv-cac-dashboard` repo). Every script:

- **finds credentials itself** — env vars first, then the standard secret files
  (`~/.secrets/meta-ads.env` for Meta, `BEEHIIV_API_KEY` /
  `~/.config/po-secrets/beehiiv.env` for beehiiv). Nothing is hardcoded and no
  plaintext secret is committed — `meta_token.enc.json` / `gh_sync.enc.json`
  ship encrypted (AES-256-GCM under the dashboard password).
- **takes `--data <dir>`** to choose the output dir; without it, the first
  existing of `action-center/data`, `client/public/data`, `data` (so the same
  command works in this repo and in the dashboard repo).

Shared plumbing lives in `_common.py`.

## The scripts

| Script | Command | Creds | Reads | Writes | Cadence |
|---|---|---|---|---|---|
| `creative_metrics.py` | `python3 scripts/creative_metrics.py [--data d]` | Meta | Meta Graph API (last-7d ads with spend: hook/hold/CTR/leads + full-res thumbnails) | `creative_metrics.json` + dated snapshot appended to `creative_metrics_history.json` (kept 16, feeds week-over-week fatigue deltas) | **daily**, after the Meta pull |
| `adset_status.py` | `python3 scripts/adset_status.py [--data d]` | Meta | Meta Graph API (all ad sets' `effective_status`) | `adset_status.json` (ACTIVE only) | **daily** — the Hub's Live-tests badges trust it |
| `test_ad_truecpa.py` | `python3 scripts/test_ad_truecpa.py [--data d] [--flags p]` | Meta + beehiiv | `test_flags_input.json` (winner → `beehiiv_segment` map), beehiiv REST (recalculate + poll each `truecpa_*` segment), Meta lifetime spend per ad | `test_ad_truecpa.json` (`{ads: {ad_id: {bh_subs, lifetime_spend, true_cpa, ltv, ltv_cac, segment}}}`) | **daily while any test is live/judgeable**. LTV = the pipeline's 7d formula (k=2.5), verified against the 2026-07-27 hand-built file. ⚠ first live run: eyeball the output — the beehiiv stats field names are read tolerantly but haven't been exercised against every API variant |
| `test_verdicts.py` | `python3 scripts/test_verdicts.py [--data d] [--flags p]` | none (pure transform) | `test_flags_input.json`, `dashboard_ad.json`, `dashboard_adset.json` | `test_verdicts.json` (benchmarks, per-test status/verdict, lessons) | **after each flags refresh** (2–3×/week or daily). Deterministic + idempotent — rerunning on the same inputs reproduces the file byte-for-byte |
| `ingest_decisions.py` | `python3 scripts/ingest_decisions.py [--inbox p] [--data d]` | none (git pull first) | `decisions-inbox.json` (repo root — written by the hosted page via the GitHub contents API) | `variation_queue.json` statuses + the human's hook edits/notes; moves entries to `processed` | **daily, after `git pull`** — prints the exact `variation_worker.sh` commands for each approval; commit+push the updated inbox afterwards |
| `variation_worker.sh` | `bash scripts/variation_worker.sh <id> build\|upload` | Meta (upload only) + a `claude` binary (PATH, or the VS Code bundle) | `variation_queue.json` option + `variation_{build,upload}_prompt.md` | built static → `built_<id>.jpg` + thumb; upload → PAUSED creative/ad-set-pair/ads in Meta, ids recorded on the option | **on demand**, per ingest output. Uploads serialize via a lock. Runs from the **dashboard repo root** (fonts/backgrounds/reference assets live there) |
| `encrypt_token.mjs` | `node scripts/encrypt_token.mjs` | reads `~/.secrets/meta-ads.env` + `~/.secrets/dashboard-pass.txt` | — | `meta_token.enc.json` (encrypted) | on token rotation only |

## Test judging — how `test_flags_input.json` gets staged

`test_verdicts.py` is deterministic; the judgment *data* is staged by a Claude
session (Meta MCP or Graph API). The rules it encodes:

1. **Judgeable when:** ~50 conversions since launch (learning exit, inferred —
   the API doesn't expose learning state) **+ 48 hours**.
2. **Pass/fail:** the test's winning ad's **Meta qualified-lead CPA** vs the
   **audience-matched winning ad set's trailing-7-complete-day Meta CPA**
   (`qualified_broad_bestperformers_adv+` for adv+, `qualified_lead_best_performers_18-45`
   for 18-45). Meta-vs-Meta — same pixel event both sides. Beehiiv true CPA and
   LTV are shown for context (that's `test_ad_truecpa.py` + the pipeline join).
3. **Resolution:** pass → ✓ promote (ad goes LIVE in the winning ad set, test
   off); fail → ✗ park (PAUSED copy into `retest_in_future_{Adv+,18-45}`, test
   off). Decisions are Nicole's, made on the dashboard — never automatic.

Staging steps for the session (per `weekly-ad-report` skill, step 8): pull each
test ad set's **daily** results (`time_increment=1`) to find the 50-conversion
crossing; pull ad-level `date_preset=maximum` for the winner's spend/CPA; pull
the two winning ad sets' trailing-7-complete-day spend/leads for benchmarks;
write it all to `refresh_inputs/test_flags_input.json` (schema: see the current
file), create/refresh a `truecpa_<ad>` beehiiv segment per winner and record its
id under `winner.beehiiv_segment`; then run `test_ad_truecpa.py` and
`test_verdicts.py`. This staging step is the natural candidate for a
`/judge-tests` skill alongside `.claude/skills/next-ads/`.

## Daily run order (after the Meta pull, in the repo with the target data dir)

```bash
git pull                                   # picks up decisions-inbox.json
python3 scripts/creative_metrics.py
python3 scripts/adset_status.py
python3 scripts/ingest_decisions.py        # then run any worker commands it prints
# while tests are live/judgeable:
python3 scripts/test_ad_truecpa.py
python3 scripts/test_verdicts.py           # after a flags refresh
git add action-center/data decisions-inbox.json && git commit && git push
```
