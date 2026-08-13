---
name: recreate-winner
description: Recreate a top-performing Pour Over ad as a fresh creative variant using REAL Pexels footage/photos (no AI-looking backgrounds). Trigger when Matt/Nicole say "/recreate-winner", "recreate the winner", "make a new version of <ad name>", "turn <ad> into a motion graphic", or "remake our best ad with real footage". Reads the winner from action-center/data/creative_metrics.json, reads its actual creative off its Meta thumbnail, sources a real matching background from Pexels, and builds a finished MP4 (or JPG) with build_creative.py. Output is a file for human review — never touches Meta.
---

# recreate-winner

Recreate a proven TPO ad as a fresh variant using **real footage/photos** (Pexels),
matching the winner's style and copy. Output is a local file for Matt to review;
this skill NEVER creates or edits anything on Meta.

## Inputs
- An ad name (e.g. `motion_snowcity_mostchristians_psych9_chaos`), or "the top ad"
  / "our best performer" (then pick the highest `meta_leads` in creative_metrics).
- Optional: a new background theme, felt-need, or format override.

## Tools (in this repo's `scripts/`)
- `pexels_fetch.py` — pull a real photo/video (free API; key in `~/.secrets/pexels.env`).
- `build_creative.py` — render the creative from a JSON spec (both documented in `scripts/README.md`).
- **Always run with `python3.12`** (system python3.9 fails Pexels/Meta SSL).

## Procedure

1. **Find the target.** Read `action-center/data/creative_metrics.json`. Match the
   ad name (or pick max `meta_leads`). Capture `thumbnail_url`, `is_video`, `ad_name`,
   and the stats (spend, meta_leads, hook_rate, hold_rate, ctr).

2. **Read the real creative.** Download the thumbnail
   (`urllib` with a browser User-Agent; the fbcdn URL must be the FULL untruncated
   string from the JSON) and **Read the image**. Extract, verbatim:
   - the **format** (9:16 vertical vs 1:1 square),
   - the **font style** — heavy white sans on dark = `boldsans`; handwritten dark on
     warm = `handwritten`,
   - the **exact copy**, split into stanzas (hook first),
   - the **background theme** (e.g. "aerial night city with snow"),
   - the **psych # + felt-need** from the ad name (see next-ads `creative-guidebook.md`).

3. **Source a REAL background.** Turn the theme into a Pexels query and list candidates:
   `python3.12 scripts/pexels_fetch.py --type video --query "<theme>" --orientation portrait --candidates 3`
   (use `--type photo` + `--orientation square` for a static). Pick one that fits the
   duration (video `duration` ≥ your ad length) and download with `--out`.
   **Default to real footage/photos — do NOT use AI-generated backgrounds** (that
   "AI look" is exactly what we're replacing; per Matt 2026-08-13).

4. **Write the spec + build.** Create a spec JSON and run
   `python3.12 scripts/build_creative.py --spec <spec>.json`. Conventions:
   - `hook_instant: true` **always** — the first stanza must be on-screen at t=0 so
     it's there the instant someone swipes to it (Matt's hard rule, 2026-08-13).
   - `scrim`: `dark` for boldsans-over-video, `warm_veil` for handwritten-over-photo.
   - `format`: match the winner (motion winners are usually `9:16`).
   - `duration` 5–6s, `fps` 15. If the clip is shorter than duration, pick a longer
     clip or lower duration (build fails if the trim exceeds the clip).
   - `out`: `action-center/data/built_<name>.mp4` (or `.jpg`).
   - Name the variant `motion_<bgtheme>_<hookslug>_psych#_feltneed`.

5. **QC (mandatory).** Extract t=0 and a mid frame with ffmpeg and **Read** both:
   - the hook must be fully visible at t=0,
   - the real footage must show through (if the whole frame is black, the text layer
     didn't render transparent — check `background.type=="video"` and rebuild),
   - no clipped/overflowing text.
   Fix and rebuild until it looks like a finished TPO ad.

6. **Hand off.** `open` the file, report the path + which real clip/photo was used
   (with its Pexels source), and note it's PAUSED/for-review only (nothing on Meta).

## Guardrails
- Output is a file only. Creating the PAUSED Meta test ad set is a separate,
  human-approved step (the Hub ✓ button / `variation_worker.sh upload`).
- Licensing: Pexels is free for commercial use, no attribution. Fine for
  scenery/nature; avoid clips with identifiable people for endorsement-style ads.
- Keep copy verbatim from the winner unless Matt asks for a new angle; if he does,
  keep the psych concept executing (don't just describe it).
