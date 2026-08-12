# Action Center — data & execution contract

`action-center/` is the hosted (GitHub Pages) copy of The Pour Over's Creative
Hub / Action Items dashboard. `index.html` is the built single-file app;
`data/` is everything it reads. This README documents the contract so the
LTV/CAC pipeline team can produce/consume these files without reading the app
source (which lives in the `ltv-cac-dashboard` repo, `client/src/pages/Hub.tsx`).

## data/ — who produces what

| File | Producer | Notes |
|------|----------|-------|
| `dashboard_overall/adset/ad/adset_date.json`, `dashboard_report.json`, `metrics_history.json`, `roas_values.json`, `dashboard_coreg.json` | the daily LTV/CAC pipeline (`full_refresh.py`) | identical schema to `client/public/data/` in the dashboard repo |
| `creative_metrics.json` | `scripts/creative_metrics.py` (Meta Graph API, last-7d ads with spend: hook/hold/CTR/leads) | |
| `adset_status.json` | `scripts/adset_status.py` (Meta Graph API: every ACTIVE ad set) | Live-tests badges go stale without it |
| `test_verdicts.json` | Claude test-judging sessions | benchmarks, per-test winners, verdicts, resolutions, `lessons` |
| `test_thumbs.json` | build/judging sessions | `{creative_id_or_built_<id>: dataURI}` thumbnails |
| `test_ad_truecpa.json` | per-ad beehiiv segment pulls | lifetime true CPA for test ads |
| `variation_queue.json` | Claude brief generation (incl. the `/next-ads` skill) + worker status updates | see schema below |
| `competitor_watch.json` | Ads Library sweeps (weekly ad report) | |
| `meta_token.enc.json`, `gh_sync.enc.json` | `scripts/encrypt_token.mjs` | AES-GCM-encrypted tokens, unlocked in-browser by the dashboard password |

> **Freshness caveat (2026-08-12):** the files here are a snapshot (currently
> Jul 27) copied from the dashboard repo — nothing updates them automatically
> yet. To make this page live, the daily pipeline needs one extra step: copy
> its `client/public/data/*.json` outputs into `action-center/data/` and push.
> This repo's `update_data.py` is unrelated (it feeds the strategic T+ cohort
> dashboard at the repo root).

## variation_queue.json schema

```jsonc
{
  "winner": {              // the champion the current batch varies (may be null)
    "name": "...", "creative_id": "...", "stats": "...", "diagnosis": "...", "note": "..."
  },
  "batch": [ <option>, ... ],
  "competitor": {          // optional: competitor-inspired concepts
    "source_note": "...",
    "batch": [ <option + based_on, their_thumb, their_aspect, library_url>, ... ]
  }
}
```

Each **option** (`batch[]` entry):

| Field | Set by | Meaning |
|-------|--------|---------|
| `id` | generator | unique: `v#` (variations), `c#` (competitor), `n#` (/next-ads gap-read briefs) |
| `dim` | generator | group label — options with the same `dim` render as one collapsible group |
| `name` | generator | the future ad name, `mediatype_hook_psych#_feltneed` convention |
| `hook` | generator (human may edit) | the creative's opening line |
| `brief` / `why` | generator | what to build / evidence for why it should win |
| `copy_note` | generator | suggested primary text (informational — uploads use house copy verbatim) |
| `status` | worker/UI | absent = awaiting decision (✓/✗ buttons show). Lifecycle: `building → built → uploading → uploaded`, or `skipped` / `rejected` / `build_failed` / `upload_failed` |
| `hook` (edited), `user_note` | the human, via the page | her edits override the generated brief; the build uses them verbatim |
| `built_img`, `built_at`, `build_note` | build worker | `/data/built_<id>.jpg` |
| `uploaded_at`, `ad_ids`, `adset_ids`, `adset_names`, `creative_meta_id` | upload worker | what was created in Meta |
| `adset_group` | generator/worker | which test ad-set pair the ad joins (hook-line changes share one `hookvariations` group) |
| `go_live_at`, `schedule_note` | scheduler modal | optional scheduled activation (see below) |

## Decision flow (any copy of the page → Meta)

1. **Decide on the page.** ✓/✗ on an option. On surfaces without a local API
   (this GitHub Pages copy, the artifact), the decision is written to
   `decisions-inbox.json` at the ROOT of this repo via the GitHub contents API,
   using a fine-grained token (contents:read/write on this repo ONLY) shipped
   encrypted as `data/gh_sync.enc.json` and unlocked by the dashboard password.
2. **Ingest.** During refresh, `scripts/ingest_decisions.py` (dashboard repo)
   applies inbox entries to `variation_queue.json` (build/upload approvals set
   `status` and carry the human's hook edits + `user_note`), then moves them to
   `processed` so they never double-apply.
3. **Build worker** (`scripts/variation_worker.sh <id> build`, headless Claude):
   composes the 1080×1080 static as HTML (house recipe: AI photo background,
   legibility veil, handwritten font; HOOK-SWAP RULE: a hook-swap changes ONLY
   the hook line, nothing else), screenshots it with headless Chrome, writes
   `data/built_<id>.jpg` + a thumbnail, sets `status: "built"`. It never
   touches Meta.
4. **Review on the page** — the built image appears on the option; ✓ again
   approves upload (optionally with a go-live time).
5. **Upload worker** (`variation_worker.sh <id> upload`, serialized by a lock):
   using the Meta Graph API token from `~/.secrets/meta-ads.env`:
   - uploads the image (`/adimages`), creates the ad creative with the
     **standard house copy verbatim** (message/headline/description/CTA →
     `anxiety.thepourover.org`, page 1958912674200535 + IG 17841411864324142),
   - ensures the test ad-set pair exists — `test_<adset_group>_<MonthDay>_18-45`
     and `..._adv+` in the Qualified Lead campaign `120239853994810224`,
     $200/day each, OFFSITE_CONVERSIONS with the winning set's promoted_object,
     created **PAUSED** (reusing the group's existing pair when present),
   - creates the ad **PAUSED in both ad sets**, records `ad_ids`/`adset_ids`.

## What can go live, precisely

- **Builds and uploads never deliver.** Everything the upload worker creates is
  PAUSED; a human activates in Ads Manager.
- **Exception 1 — scheduled go-live:** if the human picked `go_live_at` in the
  upload modal, the pair is created with that `start_time` and the ads/ad sets
  are set ACTIVE — Meta shows them as Scheduled and nothing spends before the
  chosen moment (standing rule: 12:01 AM CT next day).
- **Exception 2 — promote:** on a judgeable test, ✓-approve intentionally puts
  the winning ad LIVE in the audience-matched winning ad set
  (`qualified_broad_bestperformers_adv+` 120239853994820224 /
  `qualified_lead_best_performers_18-45` 120240614456640224) and shuts the test
  off. ✗-deny copies it PAUSED into `retest_in_future_{Adv+,18-45}`
  (120249401294620224 / 120249401327950224). These run from the page itself
  (`client/src/lib/metaActions.ts`) via a Meta token unlocked from
  `data/meta_token.enc.json` by the dashboard password (stored only in that
  browser's localStorage), or via the claude.ai artifact's Meta connector.
  Both paths execute only on an explicit human confirmation dialog.

## /next-ads skill

`.claude/skills/next-ads/` generates the next test batch: a deterministic gap
read over these data files (proven psych × felt-need × media-type combos never
combined, minus lanes that already lost) → 3–5 convention-named briefs appended
to `variation_queue.json` with no `status`, so they surface on the page for
✓/✗. Run it from a Claude Code session in this repo (or the dashboard repo —
the data dir is auto-detected). Context it relies on is versioned next to it in
`references/` (creative guidebook, naming convention, benchmark rules).
