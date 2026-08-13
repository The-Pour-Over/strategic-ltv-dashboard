# TPO Creative Studio

Local web app: generate ad creatives from the analyzer's top gaps with **real
Pexels footage/photos**, review them in a gallery, and green-button **Approve**
the good ones — each approve creates a **PAUSED** ad set + ad on Meta following
`paid-ads/LAUNCH_PLAYBOOK.md`. Nothing spends until the human Advantage+
creative AI-off pass + activation in Ads Manager.

## Run

```bash
python3.12 creative-studio/app.py     # -> http://localhost:8765
```

python3.12+ required (system 3.9 fails Pexels/Meta SSL). Also needs headless
Chrome, ffmpeg, `~/.secrets/pexels.env` (PEXELS_API_KEY) and
`~/.secrets/meta-ads.env` (META_ADS_TOKEN / META_PAGE_ID / META_AD_ACCOUNT).

A LaunchAgent (`com.tpo.creative-studio`) keeps it always-on on Matt's Mac —
`launchctl kickstart -k gui/$UID/com.tpo.creative-studio` to restart it.

## Files

| File | Role |
|---|---|
| `app.py` | zero-dependency stdlib server: /make (generate all briefs, bg thread), /status, /media (HTTP 206 ranges), /approve |
| `briefs.json` | the creative slate: gap, media (motion/static), recipe, Pexels query (+optional `index`), stanzas, music |
| `meta_launch.py` | Approve → PAUSED campaign/ad set/ad per the launch playbook (pixel 789006421963427, 180-day exclusion, UTM url_tags, ≥2s pacing). Campaign/ad-set cached in `.meta_state.json` |
| `music/` | CC0 music library (see its LICENSE.md); muxed onto motion ads by `scripts/build_creative.py add_music()` |
| `generated/` | rendered creatives + fetched backgrounds (gitignored — rebuilt on demand) |

## Creative rules (locked 2026-08-13)

- Real footage/photos only (Pexels) — no AI-generated backgrounds.
- Motion: 10s, ALL text persists the whole video (no pop-up reveals), scrim once.
- Statics: near-black handwritten ink + heavy white glow + .42 warm veil.
- Ad copy font: bold Helvetica (motion) / Shadows Into Light (static). Poppins is
  only the Studio page UI.
- Every Meta object ships PAUSED; the AI-off pass in Ads Manager is mandatory.
