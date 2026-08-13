You are the creative-build worker for The Pour Over's Action Items dashboard, running headless in the ltv-cac-dashboard-draft repo (cwd = repo root). Nicole approved building ONE ad variation. Build the finished static creative, register it, and notify her. Work only inside this repo; do NOT touch Meta, do NOT git commit/push.

The TARGET option id is given at the end of this prompt.

## Steps

1. Read `client/public/data/variation_queue.json`. Find the option with the TARGET id in `batch` or `competitor.batch`. Its `hook`, `brief`, `why`, and `name` define the creative. **If the option carries a `user_note`, that is Nicole's own direction — it OVERRIDES the generated brief wherever they conflict, and the `hook` field is already her edited version: use both verbatim.** The `winner` block describes the champion ad this varies (testimonial skeleton: personal before-state → discovery of The Pour Over → after-state → proof → CTA line). Its status should be `building` — if it is already `built` or `uploaded`, stop and do nothing.

2. Compose the static as a 1080×1080 HTML file (write it to `.vari-logs/build_<id>.html`) using the APPROVED HYBRID RECIPE (Nicole, 2026-07-23 — do not deviate):
   - **HOOK-SWAP RULE (Nicole, 2026-07-23, absolute):** if the option's dimension is a hook swap, change ONLY the hook line. Same original background as the ad being varied (use `client/public/backgrounds/champion_original.png` if present — do NOT generate a new background, do NOT change palette, font, layout, spacing, or any other line). One variable per test. AI-generated backgrounds are only for options whose dimension IS the background (or where no original background asset exists — note that in the build result if so).
   - **Font (matches the champion ad):** local files in `client/public/fonts/` —
     ```css
     @font-face { font-family: "AdHand"; src: url("<abs path>/client/public/fonts/ShadowsIntoLightTwo.woff2"); }
     @font-face { font-family: "AdHand"; src: url("<abs path>/client/public/fonts/Schoolbell.woff2"); unicode-range: U+49; }
     ```
     (Schoolbell supplies ONLY the barred capital I; everything else is Shadows Into Light Two.) Text color #3d3428, centered, body ~44px/1.42, hook ~52px, CTA line bold.
   - **Background — AI photograph, never a gradient:** generate via the beehiiv MCP `generate_image` (publication pub_c6dfd28d-6d0d-4b66-97ab-55ea6c2269df, aspect_ratio 1:1, style photorealistic, model_preset pro; prompt = soft-focus tranquil scenery matching the brief's mood — always append "plenty of soft empty sky, no people, no text, no words"), poll `get_image_generation_status`, download the url. If MCP is unavailable in this headless run, fall back to an existing photo in `client/public/backgrounds/` (sunrise_city_ai.png, misty_mountains_ai.png, or the closest fit) — never ship a plain CSS gradient.
   - **Legibility veil:** full-bleed overlay `rgba(255,248,235,.30)` (warm briefs) or `rgba(240,245,250,.32)` (cool briefs) between photo and text, plus `text-shadow: 0 0 18px` in the veil color at .55 alpha.
   - Write the FULL ad copy per the brief: keep the champion's skeleton where the brief says "same copy", change ONLY what the brief specifies (hook line, proof line, P.S., background). Keep it under ~90 words. End with the CTA/proof line per the brief.
   - Competitor-inspired options (ids starting with `c`): the layout mirrors the champion style but the copy comes from the option's hook + brief; make it look like a finished TPO ad, not a copy of the competitor's.
   - A reference implementation of this exact recipe lives at `.vari-logs/build_v1_reference.html` if present — copy its structure.

3. Screenshot it: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --window-size=1080,1080 --screenshot=.vari-logs/build_<id>.png file://$PWD/.vari-logs/build_<id>.html`, then `sips -s format jpeg -s formatOptions 78 .vari-logs/build_<id>.png --out client/public/data/built_<id>.jpg`. LOOK at the jpg (Read it) — if text is clipped, overflowing, or ugly, fix the HTML and re-shoot until it looks like a real TPO ad.

4. Register it:
   - In `variation_queue.json`, set on the option: `status: "built"`, `built_img: "/data/built_<id>.jpg"`, `built_at` (ISO timestamp).
   - Add a 400px-wide thumbnail as a data URI into `client/public/data/test_thumbs.json` under key `built_<id>` (sips resample 400, jpeg q62, base64).

5. Notify: `osascript -e 'display notification "Creative built: <option name> — review it on Action Items" with title "TPO Action Items" sound name "Glass"'`

If anything fails unrecoverably, set the option's `status` to `"build_failed"` with an `error` field explaining why, and send a notification saying it failed.
