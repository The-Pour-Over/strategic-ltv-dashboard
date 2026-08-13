#!/usr/bin/env python3
"""Per-ad beehiiv TRUE CPA for test winners -> <data>/test_ad_truecpa.json.

For every test in test_flags_input.json whose winner carries a dedicated
beehiiv segment (truecpa_* — filters utm medium = ad set, utm campaign = ad):
  1. recalculate the segment via the beehiiv REST API and poll until done
     (dynamic segments must be recalculated or they return stale counts),
  2. read member count + engagement stats,
  3. pull the ad's LIFETIME spend from the Meta Graph API (date_preset=maximum),
  4. true_cpa = lifetime_spend / beehiiv_subs; LTV via the pipeline's 7d
     formula (k=2.5): max(0, 1 - 2.5*unsub) * open * cto * 0.85 * 150 / 0.70
     — only reported at >= MIN_SUBS_FOR_LTV subscribers (rate noise below that).

Formula verified against the 2026-07-27 hand-built file (e.g. ad
120249394832660224: open .6161 x cto .413, unsub .034 -> $42.41 exact).

Usage: python3 scripts/test_ad_truecpa.py [--data <dir>] [--flags <path>]
Creds: BEEHIIV_API_KEY env (fallback ~/.config/po-secrets/beehiiv.env) +
       META_ADS_TOKEN env (fallback ~/.secrets/meta-ads.env).
"""
import argparse, datetime, json, os, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import beehiiv_key, meta_creds, resolve_data_dir

PUB = "pub_c6dfd28d-6d0d-4b66-97ab-55ea6c2269df"
ACCOUNT = "act_125820816056365"
MIN_SUBS_FOR_LTV = 20
UNSUB_K = 2.5  # 7d cohort multiplier from full_refresh.py

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=None)
ap.add_argument("--flags", default=None, help="test_flags_input.json (default: refresh_inputs/ or <data>/)")
args = ap.parse_args()
DATA = resolve_data_dir(args.data)
FLAGS = args.flags or next(
    (p for p in ("refresh_inputs/test_flags_input.json", os.path.join(DATA, "test_flags_input.json")) if os.path.exists(p)),
    None,
)
if not FLAGS:
    sys.exit("test_flags_input.json not found — pass --flags <path>")

BKEY = beehiiv_key()
MTOKEN, MVER = meta_creds()

def bh(path, method="GET"):
    req = urllib.request.Request(
        f"https://api.beehiiv.com/v2/publications/{PUB}/segments{path}",
        headers={"Authorization": f"Bearer {BKEY}"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r) if r.length != 0 else {}

def pick(d, *names):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    return None

def as_decimal(v):
    """Beehiiv stats come back as percents (61.61) in some fields, decimals in others — normalize."""
    v = float(v)
    return v / 100 if v > 1.5 else v

def segment_read(seg_id):
    """Recalculate + poll a dynamic segment, then return (members, open, cto, unsub) — rates as decimals."""
    try:
        bh(f"/{seg_id}/recalculate", method="POST")
    except Exception as e:
        print(f"  recalc {seg_id} failed ({e}) — reading as-is", file=sys.stderr)
    seg = {}
    for _ in range(30):  # up to ~5 min
        seg = pick(bh(f"/{seg_id}?expand[]=stats"), "data") or {}
        if str(pick(seg, "status", "calculation_status") or "").lower() in ("completed", "complete", ""):
            break
        time.sleep(10)
    stats = pick(seg, "stats", "metrics") or {}
    members = pick(seg, "total_results", "num_members", "active_subscriptions") or 0
    o = pick(stats, "open_rate")
    c = pick(stats, "click_through_rate", "clickthrough_rate", "cto")
    u = pick(stats, "pct_unsubscribed", "unsubscribed_rate", "unsubscribe_rate", "unsub_rate")
    return int(members), (as_decimal(o) if o is not None else None), (as_decimal(c) if c is not None else None), (as_decimal(u) if u is not None else None)

flags = json.load(open(FLAGS))
targets = {}  # ad_id -> segment
for t in flags.get("tests", []):
    w = t.get("winner") or {}
    if w.get("ad_id") and w.get("beehiiv_segment"):
        targets[w["ad_id"]] = w["beehiiv_segment"]
if not targets:
    sys.exit("no test winners with beehiiv_segment in the flags file")

# lifetime spend for all target ads in one Meta batch call
q = urllib.parse.urlencode({
    "ids": ",".join(targets),
    "fields": "insights.date_preset(maximum){spend}",
    "access_token": MTOKEN,
})
with urllib.request.urlopen(f"https://graph.facebook.com/{MVER}/?{q}", timeout=60) as r:
    meta = json.load(r)
spend = {}
for ad_id, row in meta.items():
    ins = ((row.get("insights") or {}).get("data") or [{}])[0]
    spend[ad_id] = round(float(ins.get("spend", 0) or 0), 2)

ads = {}
for ad_id, seg_id in targets.items():
    print(f"segment {seg_id} (ad {ad_id})…", file=sys.stderr)
    subs, o, c, u = segment_read(seg_id)
    sp = spend.get(ad_id, 0)
    true_cpa = round(sp / subs, 2) if subs else None
    ltv = ltv_cac = None
    if subs >= MIN_SUBS_FOR_LTV and None not in (o, c, u):
        ltv = round(max(0.0, 1 - UNSUB_K * u) * o * c * 0.85 * 150 / 0.70, 2)
        if true_cpa:
            ltv_cac = round(ltv / true_cpa, 2)
    ads[ad_id] = {"bh_subs": subs, "lifetime_spend": sp, "true_cpa": true_cpa, "ltv": ltv, "ltv_cac": ltv_cac, "segment": seg_id}

out = {"as_of": datetime.date.today().isoformat(), "min_subs_for_ltv": MIN_SUBS_FOR_LTV, "ads": ads}
path = os.path.join(DATA, "test_ad_truecpa.json")
json.dump(out, open(path, "w"), indent=1)
print(f"wrote {len(ads)} test ads -> {path}")
