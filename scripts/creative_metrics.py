#!/usr/bin/env python3
"""Pull per-ad creative metrics (hook rate, hold rate, CTR, clicks, Meta leads)
for all ads with spend in the last 7 days, straight from the Meta Graph API.

Writes <data>/creative_metrics.json (+ a dated snapshot appended to
creative_metrics_history.json for week-over-week fatigue deltas).

Usage: python3 scripts/creative_metrics.py [--data <dir>]
Creds: META_ADS_TOKEN env var, or ~/.secrets/meta-ads.env (never hardcoded).
Hook rate = 3-second plays / impressions; hold rate = ThruPlays / 3-second plays
(matches Ads Manager; same definitions as the weekly ad report).
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import meta_creds, resolve_data_dir

_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=None, help="output dir (default: auto-detect action-center/data or client/public/data)")
_args = _ap.parse_args()

ACCOUNT = "act_125820816056365"  # TPO I: Secondary
TOKEN, VER = meta_creds()
OUT = os.path.join(resolve_data_dir(_args.data), "creative_metrics.json")

def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

def action(row, kind):
    for a in row.get("actions", []):
        if a.get("action_type") == kind:
            return int(a["value"])
    return 0

params = {
    "level": "ad",
    "date_preset": "last_7d",
    "fields": "ad_id,ad_name,adset_id,adset_name,impressions,clicks,inline_link_clicks,spend,ctr,actions,video_thruplay_watched_actions",
    "filtering": json.dumps([{"field": "spend", "operator": "GREATER_THAN", "value": 0}]),
    "limit": "200",
    "access_token": TOKEN,
}
url = f"https://graph.facebook.com/{VER}/{ACCOUNT}/insights?" + urllib.parse.urlencode(params)

rows, pages = [], 0
while url and pages < 10:
    data = get(url)
    rows += data.get("data", [])
    url = data.get("paging", {}).get("next")
    pages += 1

out = []
for r in rows:
    imp = int(r.get("impressions", 0) or 0)
    if imp == 0:
        continue
    plays3s = action(r, "video_view")
    thru = r.get("video_thruplay_watched_actions") or []
    thruplays = int(thru[0]["value"]) if thru else 0
    clicks = int(r.get("inline_link_clicks", 0) or 0) or int(r.get("clicks", 0) or 0)
    leads = action(r, "lead")
    out.append({
        "ad_id": r["ad_id"],
        "ad_name": r["ad_name"],
        "adset_id": r.get("adset_id"),
        "adset_name": r.get("adset_name"),
        "spend": round(float(r.get("spend", 0) or 0), 2),
        "impressions": imp,
        "clicks": clicks,
        "ctr": round(clicks / imp * 100, 2),
        "meta_leads": leads,
        "is_video": plays3s > 0,
        "hook_rate": round(plays3s / imp * 100, 1) if plays3s else None,
        "hold_rate": round(thruplays / plays3s * 100, 1) if plays3s else None,
    })

# batch-fetch full-res creative images.
# thumbnail_url alone comes back 64x64 regardless of size params, so:
#   statics -> asset_feed_spec image hash -> /adimages lookup (original size)
#   videos  -> video_id -> /VIDEO/thumbnails (pick preferred/widest)
creatives, thumbs = {}, {}
ids = [r["ad_id"] for r in out]
for i in range(0, len(ids), 50):
    q = urllib.parse.urlencode({
        "ids": ",".join(ids[i:i + 50]),
        "fields": "creative{thumbnail_url,image_url,video_id,asset_feed_spec{images,videos}}",
        "access_token": TOKEN,
    })
    try:
        for ad_id, v in get(f"https://graph.facebook.com/{VER}/?{q}").items():
            creatives[ad_id] = v.get("creative") or {}
    except Exception as e:
        print(f"creative batch {i//50} failed: {e}", file=sys.stderr)

hashes, video_ids = {}, {}
for ad_id, c in creatives.items():
    afs = c.get("asset_feed_spec") or {}
    imgs = afs.get("images") or []
    vids = afs.get("videos") or []
    if c.get("video_id"):
        video_ids[ad_id] = str(c["video_id"])
    elif vids and vids[0].get("video_id"):
        video_ids[ad_id] = str(vids[0]["video_id"])
    elif imgs and imgs[0].get("hash"):
        hashes[ad_id] = imgs[0]["hash"]

hash_urls = {}
uniq_hashes = sorted(set(hashes.values()))
for i in range(0, len(uniq_hashes), 30):
    q = urllib.parse.urlencode({
        "hashes": json.dumps(uniq_hashes[i:i + 30]),
        "fields": "hash,url",
        "access_token": TOKEN,
    })
    try:
        for row in get(f"https://graph.facebook.com/{VER}/{ACCOUNT}/adimages?{q}").get("data", []):
            hash_urls[row["hash"]] = row.get("url")
    except Exception as e:
        print(f"adimages batch {i//30} failed: {e}", file=sys.stderr)

video_thumb = {}
uniq_vids = sorted(set(video_ids.values()))
for i in range(0, len(uniq_vids), 50):
    q = urllib.parse.urlencode({
        "ids": ",".join(uniq_vids[i:i + 50]),
        "fields": "thumbnails{uri,width,is_preferred}",
        "access_token": TOKEN,
    })
    try:
        for vid, v in get(f"https://graph.facebook.com/{VER}/?{q}").items():
            cands = (v.get("thumbnails") or {}).get("data") or []
            if cands:
                best = next((t for t in cands if t.get("is_preferred")), None) or max(cands, key=lambda t: t.get("width") or 0)
                video_thumb[vid] = best.get("uri")
    except Exception as e:
        print(f"video thumbs batch {i//50} failed: {e}", file=sys.stderr)

for r in out:
    ad_id = r["ad_id"]
    c = creatives.get(ad_id, {})
    afs = c.get("asset_feed_spec") or {}
    afs_vids = afs.get("videos") or []
    r["thumbnail_url"] = (
        video_thumb.get(video_ids.get(ad_id, ""))
        or hash_urls.get(hashes.get(ad_id, ""))
        or c.get("image_url")
        or (afs_vids[0].get("thumbnail_url") if afs_vids else None)
        or c.get("thumbnail_url")
    )

out.sort(key=lambda x: -x["spend"])
os.makedirs(os.path.dirname(OUT), exist_ok=True)
generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
with open(OUT, "w") as f:
    json.dump({"window": "last_7d", "generated_at": generated_at, "ads": out}, f, indent=1)
print(f"wrote {len(out)} ads -> {os.path.abspath(OUT)}", file=sys.stderr)

# --- archive a dated snapshot for week-over-week creative-fatigue deltas ---
# One snapshot per calendar day (latest run wins), capped at 16. The Hub's
# per-ad trend column reads this once two comparable snapshots exist.
HIST = os.path.join(os.path.dirname(OUT), "creative_metrics_history.json")
today = generated_at[:10]
try:
    hist = json.load(open(HIST)) if os.path.exists(HIST) else []
except Exception:
    hist = []
hist = [h for h in hist if h.get("date") != today]
hist.append({
    "date": today,
    "ads": {
        r["ad_id"]: {"spend": r["spend"], "ctr": r["ctr"], "hook_rate": r["hook_rate"],
                     "hold_rate": r["hold_rate"], "meta_leads": r["meta_leads"]}
        for r in out
    },
})
hist = sorted(hist, key=lambda h: h["date"])[-16:]
with open(HIST, "w") as f:
    json.dump(hist, f, indent=1)
print(f"archived snapshot {today} ({len(hist)} in history) -> {os.path.abspath(HIST)}", file=sys.stderr)
