---
name: next-ads
description: Generate the next batch of Meta ad test briefs for The Pour Over from live performance data. Trigger when Nicole or Matt's team says "/next-ads", "generate the next test batch", "queue new ad concepts", "the test queue is empty", or asks what ads to test next. Reads the action-center data files, does the gap read (proven psych-concept x felt-need x media-type combos never yet combined, screening out lanes that already lost), and writes 3-5 convention-named briefs into variation_queue.json so they appear on the Creative Hub / Action Items page with ✓ build / ✗ skip buttons.
---

# /next-ads — generate the next test batch

You generate **briefs only**. Never call the Meta API, never change any option's
`status`, never touch `winner`, `competitor`, or existing batch entries. The
human approves each brief on the dashboard (✓ build), and the existing worker
pipeline builds and uploads it — see `action-center/README.md` for that contract.

## Context you must load first

Read the three files in `references/` next to this skill:
- `creative-guidebook.md` — the 17 psychological concepts + 16 felt needs (the only allowed values)
- `naming-convention.md` — `mediatype_hook_psych#_feltneed` (names must parse, or the pattern read goes blind)
- `benchmark-rules.md` — what "true CPA" and "benchmark" mean on this account

## Steps

1. **Run the gap read** (deterministic, no judgment involved):
   ```bash
   python3 "<this skill's base dir>/gap_read.py"          # auto-finds the data dir
   python3 "<this skill's base dir>/gap_read.py" --data <dir>   # or point it explicitly
   ```
   It reads `creative_metrics.json`, `dashboard_ad.json`, `test_verdicts.json`,
   `adset_status.json`, `variation_queue.json` from `action-center/data/` (or
   `client/public/data/` when run in the dashboard repo) and outputs: proven
   components with subs + true CPA, lost lanes, live tests, in-flight queue
   items, the verbatim `lessons`, ranked `candidates`, and `next_free_id`.

2. **Check freshness.** If `report_generated_at` (or the `creative_window` end)
   is more than 7 days old, WARN in your final report; if more than 14 days old,
   STOP and tell the user to refresh the data first — briefs from stale data
   waste real ad spend.

3. **Pick 3–5 candidates.** The gap read ranks them; you apply judgment:
   - Prefer `fresh_pair: true` (psych × felt need never tested in any format).
   - Diversify: at least 2 media types across the batch; never more than 2
     briefs on the same felt need.
   - Honor every entry in `lessons` (e.g. "re-skinning a winner doesn't beat
     the winner" means no brief may be a cosmetic variation of a current top ad).
   - Skip anything semantically close to `live_test_adsets` or `in_flight_queue`
     items, even when the trait triple technically differs.

4. **Write each brief** with these fields:
   - `id`: `next_free_id` from the gap read, then increment (`n1`, `n2`, …). Never reuse an existing id.
   - `dim`: `"Next concepts — <Mon DD> gap read"` (one shared dim for the batch; it renders as one group on the Hub).
   - `name`: per the naming convention. The hook slug = first 2–4 words of your hook line, lowercase, no spaces.
   - `hook`: the actual opening line the creative will lead with — write it in
     TPO's voice (warm, plain, Christ-first; 3rd-grade reading level per
     concept #17), and make it EXECUTE the psych concept, not describe it.
   - `brief`: 2–3 sentences — what the static/video shows and its copy
     structure. For statics assume the house recipe (photo background, veil,
     handwritten font) unless the concept demands otherwise.
   - `why`: evidence-backed, with the numbers from the gap read — e.g.
     "#11 Damaging admission is the only recent test win; anxiety is the #1
     felt need (5,733 subs @ $5.12); the pair has never met in a motiongraphic."
   - `copy_note`: a suggested single-line primary text for the Meta ad. Note:
     the upload worker uses the standard house copy verbatim unless told
     otherwise, so this is a suggestion for the human, not an instruction.
   - No `status` field — absent status is what makes the ✓/✗ buttons appear.

5. **Append to the queue.** Add the briefs to `batch` in `variation_queue.json`
   (the data dir the gap read reported). Do not modify anything else in the
   file. Re-read and `json.load` the file after writing to prove it still parses.

6. **Report.** Show the user a compact table: name · hook · why (with numbers),
   plus what you screened out (lost lanes honored, in-flight overlaps skipped)
   and the data window the read was based on. Remind them the briefs are now on
   the Creative Hub under Ready to test, pending ✓.

## Guardrails

- Data files are read-only except `variation_queue.json`, and there only `batch` appends.
- If `variation_queue.json` is missing, create it as `{"winner": null, "batch": [<briefs>]}` and say so.
- If fewer than 3 candidates survive screening, deliver however many are real —
  never pad with weak combos; say why the pool is thin instead.
- Psych numbers and felt needs must come from the guidebook lists verbatim.
