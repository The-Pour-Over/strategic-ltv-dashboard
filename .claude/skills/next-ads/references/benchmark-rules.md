# True-CPA benchmark rules (test verdicts)

How a test wins or loses on this account. The /next-ads skill needs these to
write honest "why" lines; the Action Center enforces them at decision time.

## True CPA

**True CPA = Meta spend ÷ beehiiv-attributed subscribers** — never Meta's own
cost-per-lead. Attribution comes from beehiiv UTM custom fields; for test ads
with per-ad beehiiv segments the subscriber count is lifetime for that ad
(`test_ad_truecpa.json`), otherwise it's the 7d cohort join from
`dashboard_ad.json`. A `~` on the dashboard marks Meta-only counts (an ad
running without standard UTMs).

## The benchmark

Each audience's benchmark is **its own winning ad set's 7d true CPA**:

| Audience | Winning ad set | Benchmark source |
|----------|----------------|------------------|
| `adv+` | `qualified_broad_bestperformers_adv+` (120239853994820224) | `test_verdicts.json → benchmarks["adv+"].beehiiv_cac_7d` |
| `18-45` | `qualified_lead_best_performers_18-45` (120240614456640224) | `test_verdicts.json → benchmarks["18-45"].beehiiv_cac_7d` |

Benchmarks are audience-matched — an 18-45 test is never judged against the
adv+ number (they routinely differ by $1–2).

## The verdict flow

1. A test leaves "learning" at ~50 attributed subs (`LEARNING_THRESHOLD`).
2. 48h later it becomes **judgeable**: its winner's true CPA vs the
   audience-matched benchmark.
3. **Beats benchmark** → ✓ promote: the ad is copied into the winning ad set
   (this is the one action that intentionally goes live) and the test shuts off.
4. **Misses benchmark** → ✗ park: a PAUSED copy goes to the age-matched
   `retest_in_future_{Adv+,18-45}` ad set; nothing goes live.
5. Resolved tests leave the decision queue; their outcome stays on the Live
   tests rows and in `test_verdicts.json` (`resolution`, `lessons`).

## Spend/launch standing rules (Nicole)

- New test launches are scheduled for **12:01 AM CT the next day**, set via
  `start_time` at ad-set creation (Meta can't add it later).
- Primary text on uploads is the standard house copy (see
  `action-center/README.md`) unless a human overrides it.
