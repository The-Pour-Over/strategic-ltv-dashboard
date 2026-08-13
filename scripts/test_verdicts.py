#!/usr/bin/env python3
"""
test_verdicts.py — build client/public/data/test_verdicts.json for the /actions page.

Nicole's rule (2026-07-21): a concluded test's WINNING ad must beat the matching
age group's winning-ad-set average CPA over the last 7 days (Meta qualified-lead
CPA vs Meta qualified-lead CPA — same event on both sides). A test can be judged
48 hours after leaving Meta's learning phase (inferred: ~50 conversions since
launch; the API doesn't expose learning state). Failures queue for her approval
before the winning ad is copied (paused) into the `retest_in_future` ad set and
the test is turned off.

Inputs
  refresh_inputs/test_flags_input.json   Meta-pulled facts (benchmarks + tests).
      Refresh via MCP: adset-level daily results (time_increment=1) to find the
      50-conversion crossing per test, ad-level `maximum` for winner CPA, and
      the two winning ad sets' trailing-7-complete-day spend/leads for the
      benchmarks. See ~/.claude/skills/weekly-ad-report/SKILL.md step 8.
  client/public/data/dashboard_ad.json     per-ad beehiiv LTV (pipeline output)
  client/public/data/dashboard_adset.json  winning-ad-set LTV/CAC context

The LTV join leans on the existing pipeline's equations — tactical_ltv_per_sub /
ltv_cac_ratio are read as-is, never recomputed here. Note the pipeline's `cac`
uses beehiiv-attributed subs (all new subs), while verdicts use Meta qualified
leads; both are shown, only Meta-vs-Meta decides pass/fail.

True CPA (added 2026-07-22, per Nicole): same equation as the pipeline's per-ad
CAC — the ad's spend ÷ beehiiv subs attributed to it (utm medium = ad set,
utm campaign = ad). For test winners the beehiiv counts come from dedicated
"truecpa_*" segments (ids in test_flags_input.json under winner.beehiiv_segment);
refresh them with recalculate_segment via MCP, wait for last_processed_at to
advance, then update winner.beehiiv_subs_lifetime and rerun this script.
Winning-ad-set true CPA = the pipeline's own 7d `cac`, read from
dashboard_adset.json. Meta CPA counts only the qualified-lead pixel event, so
it runs higher than true CPA on both sides; pass/fail still compares Meta CPA
to Meta CPA until Nicole says otherwise.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import resolve_data_dir

_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=None, help="data dir (default: auto-detect action-center/data or client/public/data)")
_ap.add_argument("--flags", default=None, help="test_flags_input.json (default: refresh_inputs/ or <data>/)")
_args = _ap.parse_args()

DATA = resolve_data_dir(_args.data)
INPUT = _args.flags or next(
    (p for p in ("refresh_inputs/test_flags_input.json", os.path.join(DATA, "test_flags_input.json")) if os.path.exists(p)),
    "refresh_inputs/test_flags_input.json",
)
OUTPUT = os.path.join(DATA, "test_verdicts.json")

LTV_COHORT = "7d"  # cohort used for LTV context columns


def load(path):
    with open(path) as f:
        return json.load(f)


def ltv_lookup(ad_rows, ad_name):
    """Find beehiiv-attributed LTV for an ad by utm_campaign name.

    Exact match first; then prefix match to catch variant suffixes
    (e.g. Meta ad "B1a_test_video_..." vs beehiiv utm "B1_test_video_...").
    """
    candidates = [r for r in ad_rows if r.get("cohort") == LTV_COHORT]
    for r in candidates:
        if r.get("ad_name") == ad_name:
            return r, "exact"

    def tail(name):
        # drop the variant prefix token: "B1a_test_video_x" -> "test_video_x"
        parts = (name or "").lower().split("_")
        return "_".join(parts[1:]) if len(parts) > 2 else ""

    for r in candidates:
        t = tail(r.get("ad_name"))
        if t and len(t) >= 10 and t == tail(ad_name):
            return r, "fuzzy"
    return None, None


def main():
    flags = load(INPUT)
    ad_rows = load(os.path.join(DATA, "dashboard_ad.json"))
    adset_rows = load(os.path.join(DATA, "dashboard_adset.json"))

    benchmarks = {}
    for aud, b in flags["benchmarks"].items():
        ctx = next(
            (r for r in adset_rows
             if r.get("adset_name") == b["adset_name"] and r.get("cohort") == LTV_COHORT),
            {},
        )
        benchmarks[aud] = {
            **b,
            "beehiiv_cac_7d": ctx.get("cac"),
            "beehiiv_ltv_7d": ctx.get("tactical_ltv_per_sub"),
            "ltv_cac_7d": ctx.get("ltv_cac_ratio"),
            "beehiiv_subs_7d": ctx.get("num_subscribers"),
        }

    tests = []
    for t in flags["tests"]:
        row = dict(t)
        bench = benchmarks.get(t["audience"], {})
        w = t.get("winner")
        if w:
            bh_subs = w.get("beehiiv_subs_lifetime")
            true_cpa = round(w["spend"] / bh_subs, 2) if bh_subs else None
            # Card LTV MUST be audience/test-matched (Nicole 2026-07-22): compute
            # with the pipeline's v12 formula from the winner's own truecpa_*
            # segment metrics — the engagement of THIS test's subscribers.
            # k=2.5 matches the 7d-age cohort; ratio uses true CPA.
            ltv = ratio = None
            match = None
            sm = w.get("segment_metrics")
            if sm:
                k = 2.5
                ltv = round(
                    max(0, 1 - k * sm["unsub_rate"]) * sm["open_rate"] * sm["cto"] * 0.85 * 150 / 0.70, 2
                )
                ratio = round(ltv / true_cpa, 2) if true_cpa else None
                match = "segment"
            # Pipeline join is CONTEXT ONLY: it describes a copy of the creative
            # running in a WINNING ad set (possibly a different audience), never
            # the card verdict. Ignore rows under 20 subs (name-match noise).
            ltv_row, join_match = ltv_lookup(ad_rows, w["ad_name"])
            min_subs = 10 if join_match == "exact" else 20
            if ltv_row and (ltv_row.get("num_subscribers") or 0) < min_subs:
                ltv_row, join_match = None, None
            promoted_copy = (
                {
                    "adset_name": ltv_row.get("adset_name"),
                    "ltv": ltv_row.get("tactical_ltv_per_sub"),
                    "ltv_cac": ltv_row.get("ltv_cac_ratio"),
                    "subs_7d": ltv_row.get("num_subscribers"),
                    "match": join_match,
                }
                if ltv_row
                else None
            )
            if ltv is None and promoted_copy:
                # last resort when no segment metrics exist yet
                ltv, ratio, match = promoted_copy["ltv"], promoted_copy["ltv_cac"], join_match
            row["winner"] = {
                **w,
                "true_cpa": true_cpa,
                "beehiiv_ltv_7d": ltv,
                "beehiiv_ltv_cac_7d": ratio,
                "beehiiv_subs_7d": bh_subs,
                "ltv_match": match,
                "promoted_copy": promoted_copy,
            }
        true_cpa = row.get("winner", {}).get("true_cpa") if w else None
        true_bench = bench.get("beehiiv_cac_7d")
        if t["status"] == "judgeable" and true_cpa and true_bench:
            # 2026-07-22 per Nicole: judge on true CPA (beehiiv-attributed), not Meta
            row["verdict"] = "pass" if true_cpa <= true_bench else "fail"
            row["pct_over_benchmark"] = round((true_cpa - true_bench) / true_bench * 100, 1)
            row["verdict_basis"] = "true_cpa"
        elif t["status"] == "judgeable" and w and bench.get("meta_cpa_7d"):
            # fallback when a winner has no truecpa_* segment count yet
            row["verdict"] = "pass" if w["meta_cpa"] <= bench["meta_cpa_7d"] else "fail"
            row["pct_over_benchmark"] = round(
                (w["meta_cpa"] - bench["meta_cpa_7d"]) / bench["meta_cpa_7d"] * 100, 1
            )
            row["verdict_basis"] = "meta_cpa"
        else:
            row["verdict"] = None
        tests.append(row)

    out = {
        "as_of": flags["as_of"],
        "account_id": flags["account_id"],
        "retest_adset_id": flags["retest_adset_id"],
        "ltv_cohort": LTV_COHORT,
        "benchmarks": benchmarks,
        "tests": tests,
        # hand-authored weekly takeaways (2-4 bullets, each with example ad
        # names as evidence) — written in test_flags_input.json during the
        # refresh; the Hub renders these instead of raw per-test rows
        "lessons": flags.get("lessons", []),
        "flagged_count": sum(1 for t in tests if t["verdict"] == "fail"),
    }
    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUTPUT}: {out['flagged_count']} flagged, {len(tests)} tests")


if __name__ == "__main__":
    main()
