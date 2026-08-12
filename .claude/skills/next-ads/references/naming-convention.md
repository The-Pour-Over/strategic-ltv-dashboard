# Ad naming convention — `mediatype_hook_psych#_feltneed`

Every ad name is data. The dashboards parse names into traits (media type,
hook, psych concept, felt need) and aggregate them into the "What the data
says" pattern read — an ad that doesn't follow the convention is invisible to
that analysis (currently ~22 of 131 converting ads are unparseable).

## Format

```
mediatype_hook_psych#_feltneed
static_ifyourechristian_psych9_anxiety
motiongraphic_iusedtostart_psych11_resentment
```

| Slot | Rule | Allowed values |
|------|------|----------------|
| `mediatype` | first token | `static`, `ugc`, `video`, `motiongraphic`, `shortvideo` |
| `hook` | first 2–4 words of the hook line, lowercase, no spaces | free text (no underscores inside) |
| `psych#` | literally `psych` + the concept number | 1–17, from the guidebook |
| `feltneed` | the felt need addressed, lowercase | the 16 guidebook emotions |

## Parse rules (mirror of `client/src/lib/adTraits.ts` and `gap_read.py`)

- media type: first match of `static|ugc|video|motiongraphic|motion_graphic|motion|shortvideo`
  between underscores (`motion`/`motion_graphic` normalize to `motiongraphic`)
- psych: `psych(\d+)`
- felt need: the `[a-z]+` token immediately after `psych#_`
- hook: everything between the media type and `psych#`

Keep the two implementations in sync if the convention ever changes.

## Test ad-set names

Test ad sets (not ads) follow `test_<adset_group>_<MonthDay>_{18-45,adv+}`,
e.g. `test_hookvariations_jul24_adv+` — see `action-center/README.md`.
