#!/usr/bin/env python3
"""Deterministic half of the /next-ads skill: the GAP READ.

Reads the action-center data files and outputs (JSON, stdout) the proven
creative components, the lanes already tested / lost / live / in-flight,
and ranked candidate combos that are proven separately but never combined.
Claude (the skill) turns the top candidates into convention-named briefs.

Reads (all optional except creative_metrics + dashboard_ad):
  creative_metrics.json   last-7d per-ad spend/clicks/meta_leads (Meta API)
  dashboard_ad.json       per-ad beehiiv attribution incl. 7d cohort rows
  test_verdicts.json      finished tests: winner names, resolutions, lessons
  adset_status.json       ad sets ACTIVE in Meta right now
  variation_queue.json    briefs already queued / building / uploaded

Usage: python3 gap_read.py [--data <dir>]
Data dir auto-detect order: action-center/data, client/public/data, data
(relative to cwd), so the same skill runs in strategic-ltv-dashboard,
ltv-cac-dashboard(-draft), or any checkout that carries these files.
"""
import argparse, json, os, re, sys

PSYCH_NAMES = {
    1: "Reciprocity", 2: "Commitment", 3: "Social proof", 4: "Liking",
    5: "Authority", 6: "Scarcity", 7: "Unity", 8: "Headline dominance",
    9: "Selective filtering", 10: "Zeigarnik (open loop)", 11: "Damaging admission",
    12: "Empirical proof", 13: "Un-copyable proof", 14: "Reason why",
    15: "Status signaling", 16: "Singular path", 17: "Cognitive fluency",
}
MEDIA_RE = re.compile(r"(?:^|_)(static|ugc|video|motiongraphic|motion_graphic|motion|shortvideo)(?:_|$)")

def parse_traits(ad_name):
    """Mirror of client/src/lib/adTraits.ts parseTraits — keep in sync."""
    t = {}
    lower = ad_name.lower()
    media = MEDIA_RE.search(lower)
    if media:
        m = media.group(1).replace("motion_graphic", "motiongraphic")
        t["mediaType"] = "motiongraphic" if m == "motion" else m
    psych = re.search(r"psych(\d+)", lower)
    if psych:
        t["psych"] = int(psych.group(1))
        after = re.match(r"^_([a-z]+)", lower[lower.index(psych.group(0)) + len(psych.group(0)):])
        if after:
            t["feltNeed"] = after.group(1)
    return t

def load(data_dir, name):
    p = os.path.join(data_dir, name)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)

def find_data_dir(explicit):
    if explicit:
        return explicit
    for cand in ("action-center/data", "client/public/data", "data"):
        if os.path.exists(os.path.join(cand, "creative_metrics.json")):
            return cand
    sys.exit("gap_read: no data dir found (looked for creative_metrics.json in action-center/data, client/public/data, data)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    args = ap.parse_args()
    d = find_data_dir(args.data)

    creative = (load(d, "creative_metrics.json") or {}).get("ads", [])
    ad_cohorts = load(d, "dashboard_ad.json") or []
    verdicts = load(d, "test_verdicts.json") or {}
    active = (load(d, "adset_status.json") or {}).get("active", {})
    queue = load(d, "variation_queue.json") or {}
    report = load(d, "dashboard_report.json") or {}

    # --- attribute subs to each converting ad (7d cohort, same join as the Hub) ---
    beehiiv = {}
    for a in ad_cohorts:
        if a.get("cohort") == "7d":
            beehiiv[f"{a.get('adset_name','').strip()}|{a.get('ad_name','').strip()}"] = a
    rows = []
    for c in creative:
        b = beehiiv.get(f"{(c.get('adset_name') or '').strip()}|{c.get('ad_name','').strip()}")
        subs = b["num_subscribers"] if b and b.get("num_subscribers", 0) > 0 else c.get("meta_leads") or 0
        rows.append({"ad_name": c["ad_name"], "subs": subs, "spend": c.get("spend") or 0})

    # --- aggregate proven components ---
    def aggregate(key_of):
        m = {}
        for r in rows:
            k = key_of(parse_traits(r["ad_name"]))
            if not k or r["subs"] <= 0:
                continue
            e = m.setdefault(k, {"ads": 0, "subs": 0, "spend": 0.0})
            e["ads"] += 1
            e["subs"] += r["subs"]
            e["spend"] += r["spend"]
        out = [
            {"key": k, "ads": e["ads"], "subs": e["subs"],
             "true_cpa": round(e["spend"] / e["subs"], 2) if e["subs"] else None}
            for k, e in m.items()
        ]
        return sorted(out, key=lambda x: -x["subs"])

    by_psych = aggregate(lambda t: t.get("psych"))
    by_need = aggregate(lambda t: t.get("feltNeed"))
    by_media = aggregate(lambda t: t.get("mediaType"))

    # --- names already occupying a lane: every ad/test/queue/live-adset name ---
    seen_names = [r["ad_name"] for r in rows]
    seen_names += [t.get("test", "") for t in verdicts.get("tests", [])]
    seen_names += [(t.get("winner") or {}).get("ad_name", "") for t in verdicts.get("tests", [])]
    seen_names += list(active.keys())
    for opt in (queue.get("batch") or []) + ((queue.get("competitor") or {}).get("batch") or []):
        seen_names.append(opt.get("name", ""))
    tested_triples, tested_pairs = set(), set()
    for n in seen_names:
        t = parse_traits(n or "")
        if t.get("psych") and t.get("feltNeed"):
            tested_pairs.add((t["psych"], t["feltNeed"]))
            if t.get("mediaType"):
                tested_triples.add((t["mediaType"], t["psych"], t["feltNeed"]))

    # --- lanes that LOST: parked test winners (don't rerun losses) ---
    lost_pairs = set()
    for t in verdicts.get("tests", []):
        res = t.get("resolution") or {}
        if res.get("action") == "parked":
            for n in (t.get("test", ""), (t.get("winner") or {}).get("ad_name", "")):
                tr = parse_traits(n or "")
                if tr.get("psych") and tr.get("feltNeed"):
                    lost_pairs.add((tr["psych"], tr["feltNeed"]))

    # --- candidates: proven psych x proven need x proven media, never combined ---
    MIN_SUBS = 100  # a component must have converted at least this many 7d subs to count as proven
    psychs = [p for p in by_psych if p["subs"] >= MIN_SUBS][:6]
    needs = [n for n in by_need if n["subs"] >= MIN_SUBS][:6]
    medias = [m for m in by_media if m["subs"] >= MIN_SUBS][:4]
    total_subs = sum(r["subs"] for r in rows) or 1
    candidates = []
    for p in psychs:
        for n in needs:
            pair = (p["key"], n["key"])
            if pair in lost_pairs:
                continue
            for m in medias:
                if (m["key"], p["key"], n["key"]) in tested_triples:
                    continue
                fresh_pair = pair not in tested_pairs
                score = (p["subs"] + n["subs"] + 0.5 * m["subs"]) / total_subs
                candidates.append({
                    "mediaType": m["key"],
                    "psych": p["key"],
                    "psychLabel": f"#{p['key']} {PSYCH_NAMES.get(p['key'], '?')}",
                    "feltNeed": n["key"],
                    "fresh_pair": fresh_pair,  # psych x need never tested at all (not just this media)
                    "score": round(score, 3),
                    "evidence": {
                        "psych": {"subs": p["subs"], "true_cpa": p["true_cpa"], "ads": p["ads"]},
                        "need": {"subs": n["subs"], "true_cpa": n["true_cpa"], "ads": n["ads"]},
                        "media": {"subs": m["subs"], "true_cpa": m["true_cpa"], "ads": m["ads"]},
                    },
                })
    candidates.sort(key=lambda c: (-c["fresh_pair"], -c["score"]))

    existing_ids = [o.get("id", "") for o in (queue.get("batch") or [])]
    n_ids = [int(m.group(1)) for i in existing_ids if (m := re.match(r"^n(\d+)$", i))]
    print(json.dumps({
        "data_dir": d,
        "report_generated_at": report.get("generated_at"),
        "creative_window": (load(d, "creative_metrics.json") or {}).get("window"),
        "verdicts_as_of": verdicts.get("as_of"),
        "proven": {"by_psych": by_psych, "by_need": by_need, "by_media": by_media},
        "lost_pairs": sorted([f"psych{p}_{n}" for p, n in lost_pairs]),
        "live_test_adsets": [k for k in active if k.lower().startswith("test_")],
        "in_flight_queue": [
            {"id": o.get("id"), "name": o.get("name"), "status": o.get("status")}
            for o in (queue.get("batch") or []) + ((queue.get("competitor") or {}).get("batch") or [])
        ],
        "lessons": [l.get("lesson") for l in verdicts.get("lessons", [])],
        "next_free_id": f"n{max(n_ids) + 1 if n_ids else 1}",
        "candidates": candidates[:12],
    }, indent=1))

if __name__ == "__main__":
    main()
