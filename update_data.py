"""
Monthly beehiiv data updater for Strategic LTV Dashboard
Recalculates the T+ cohort segments, fetches their stats, and updates index.html

The T+ segments are static segments with RELATIVE date windows
(signup_date <= NOW() - INTERVAL 'X days'), so they must be RECALCULATED
before reading — otherwise this pulls the same numbers forever.
"""
import os
import re
import sys
import time
import requests
from datetime import date

API_KEY = os.environ["BEEHIIV_API_KEY"]
PUB_ID  = "pub_c6dfd28d-6d0d-4b66-97ab-55ea6c2269df"
BASE    = "https://api.beehiiv.com/v2"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

CHANNELS = ["Meta", "Referrals", "Newsletter", "Google", "Overall"]
WINDOWS = [
    ("T+25 to T+35", 1),
    ("T+55 to T+65", 2),
    ("T+85 to T+95", 3),
    ("T+115 to T+125", 4),
    ("T+145 to T+155", 5),
    ("T+175 to T+185", 6),
    ("T+205 to T+215", 7),
    ("T+235 and on", 8),
]

def canon(name):
    """Normalize a segment name for matching.

    Real segment names are lowercase ('meta T+25 to T+35') and include
    variants: 'newsletters T+115 to T+125' (plural) and
    'overall t+235 and on' (lowercase t). The old exact-match dict
    matched nothing and zeroed the dashboard (July 2026)."""
    n = " ".join(name.strip().lower().split())
    n = n.replace("newsletters ", "newsletter ")
    return n

# canon name -> (channel, window index)
TARGETS = {}
for wi, (wname, _) in enumerate(WINDOWS):
    for channel in CHANNELS:
        key = canon(f"{'newsletter' if channel == 'Newsletter' else channel.lower()} {wname}")
        TARGETS[key] = (channel, wi)

def fetch_all_segments():
    segments = {}
    page = 1
    while True:
        r = requests.get(f"{BASE}/publications/{PUB_ID}/segments",
                         headers=HEADERS,
                         params={"limit": 100, "page": page})
        r.raise_for_status()
        data = r.json()
        for seg in data.get("data", []):
            segments[seg["name"]] = seg["id"]
        if page >= data.get("total_pages", 1):
            break
        page += 1
    return segments

def match_targets(all_segments):
    """Map each (channel, window) to a segment id, skipping '(N)' duplicates."""
    found = {}
    for seg_name, seg_id in all_segments.items():
        if "(" in seg_name:  # numbered duplicates from past manual re-creation
            continue
        key = canon(seg_name)
        if key in TARGETS:
            found[TARGETS[key]] = (seg_name, seg_id)
    missing = [t for t in TARGETS.values() if t not in found]
    for channel, wi in missing:
        print(f"  WARNING: no segment found for {channel} / {WINDOWS[wi][0]}")
    return found

def recalculate_segment(seg_id):
    """Trigger a recalculation. Endpoint verb differs across API versions;
    try PUT then POST. Non-fatal on failure (stats will just be stale)."""
    for verb in (requests.put, requests.post):
        try:
            r = verb(f"{BASE}/publications/{PUB_ID}/segments/{seg_id}/recalculate",
                     headers=HEADERS)
            if r.status_code < 300:
                return True
        except requests.RequestException:
            pass
    return False

def fetch_segment_stats(seg_id):
    r = requests.get(f"{BASE}/publications/{PUB_ID}/segments/{seg_id}",
                     headers=HEADERS)
    r.raise_for_status()
    d = r.json().get("data", {})
    stats = d.get("stats", d)
    return {
        "subs":           d.get("total_results", stats.get("subscriber_count", 0)) or 0,
        "openRate":       round(stats.get("open_rate", 0) or 0, 4),
        "CTR":            round(stats.get("click_through_rate", 0) or 0, 4),
        "unsubRate":      round(stats.get("pct_unsubscribed", 0) or 0, 4),
        "premiumRate":    round(stats.get("pct_premium", 0) or 0, 4),
        "referralRate":   round(stats.get("pct_referring", 0) or 0, 4),
        "refsPerReferrer": round(stats.get("average_referrals_per_referrer", 0) or 0, 2),
    }

def build_grid(found):
    grid = [[None]*len(CHANNELS) for _ in WINDOWS]
    for (channel, wi), (seg_name, seg_id) in found.items():
        print(f"  Fetching {seg_name}...")
        ci = CHANNELS.index(channel)
        stats = fetch_segment_stats(seg_id)
        uuid = seg_id.split("seg_", 1)[-1]
        stats["segUrl"] = f"https://app.beehiiv.com/segments/{uuid}/edit"
        grid[wi][ci] = stats
    return grid

def build_js(grid):
    lines = ["const timeWindows = ["]
    for wi, (wname, month) in enumerate(WINDOWS):
        lines.append(f'  {{ name: "{wname}", month: {month}, channels: [')
        for ci, channel in enumerate(CHANNELS):
            s = grid[wi][ci] or {"subs": 0, "openRate": 0, "CTR": 0, "unsubRate": 0,
                                 "premiumRate": 0, "referralRate": 0, "refsPerReferrer": 0}
            overall = ", isOverall: true" if channel == "Overall" else ""
            seg_url = f', segUrl: "{s["segUrl"]}"' if s.get("segUrl") else ""
            lines.append(
                f'    {{ channel: "{channel}", subs: {s["subs"]}, '
                f'openRate: {s["openRate"]}, CTR: {s["CTR"]}, '
                f'unsubRate: {s["unsubRate"]}, premiumRate: {s["premiumRate"]}, '
                f'referralRate: {s["referralRate"]}, refsPerReferrer: {s["refsPerReferrer"]}{seg_url}{overall} }},'
            )
        lines.append("  ]},")
    lines.append("];")
    return "\n".join(lines)

def update_html(new_js, pull_date):
    with open("index.html", "r") as f:
        html = f.read()
    html = re.sub(r"const timeWindows = \[.*?\];", new_js, html, flags=re.DOTALL)
    html = re.sub(r"Data pulled [A-Za-z]+ \d+, \d{4}", f"Data pulled {pull_date}", html)
    with open("index.html", "w") as f:
        f.write(html)

if __name__ == "__main__":
    print("Fetching segments list...")
    all_segs = fetch_all_segments()
    print(f"Found {len(all_segs)} total segments")

    found = match_targets(all_segs)
    print(f"Matched {len(found)}/{len(TARGETS)} channel/window segments")
    if len(found) < len(TARGETS) * 0.5:
        sys.exit("ABORT: matched fewer than half the expected segments; "
                 "refusing to overwrite the dashboard.")

    print("Triggering recalculation of all matched segments...")
    ok = sum(recalculate_segment(seg_id) for _, seg_id in found.values())
    print(f"  {ok}/{len(found)} recalcs accepted")
    if ok:
        print("Waiting 5 minutes for beehiiv to reprocess...")
        time.sleep(300)

    print("Fetching stats...")
    grid = build_grid(found)

    total_subs = sum((cell or {}).get("subs", 0) for row in grid for cell in row)
    if total_subs == 0:
        sys.exit("ABORT: every segment returned 0 subscribers — data looks wrong; "
                 "refusing to overwrite the dashboard. (This guard exists because "
                 "the July 2026 run silently zeroed the page.)")

    print("Building JS data...")
    new_js = build_js(grid)
    pull_date = date.today().strftime("%B %-d, %Y")
    print(f"Updating index.html (date: {pull_date})...")
    update_html(new_js, pull_date)
    print("Done!")
