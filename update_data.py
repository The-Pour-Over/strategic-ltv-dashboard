"""
Monthly beehiiv data updater for Strategic LTV Dashboard
Fetches T+ segment data and updates index.html
"""
import os
import re
import json
import requests
from datetime import date

API_KEY = os.environ["BEEHIIV_API_KEY"]
PUB_ID  = "pub_c6dfd28d-6d0d-4b66-97ab-55ea6c2269df"
BASE    = "https://api.beehiiv.com/v2"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

SEGMENT_NAMES = {
    "Meta T+25 to T+35": ("Meta", 0),
    "Referrals T+25 to T+35": ("Referrals", 0),
    "Newsletter T+25 to T+35": ("Newsletter", 0),
    "Google T+25 to T+35": ("Google", 0),
    "Overall T+25 to T+35": ("Overall", 0),
    "Meta T+55 to T+65": ("Meta", 1),
    "Referrals T+55 to T+65": ("Referrals", 1),
    "Newsletter T+55 to T+65": ("Newsletter", 1),
    "Google T+55 to T+65": ("Google", 1),
    "Overall T+55 to T+65": ("Overall", 1),
    "Meta T+85 to T+95": ("Meta", 2),
    "Referrals T+85 to T+95": ("Referrals", 2),
    "Newsletter T+85 to T+95": ("Newsletter", 2),
    "Google T+85 to T+95": ("Google", 2),
    "Overall T+85 to T+95": ("Overall", 2),
    "Meta T+115 to T+125": ("Meta", 3),
    "Referrals T+115 to T+125": ("Referrals", 3),
    "Newsletter T+115 to T+125": ("Newsletter", 3),
    "Google T+115 to T+125": ("Google", 3),
    "Overall T+115 to T+125": ("Overall", 3),
    "Meta T+145 to T+155": ("Meta", 4),
    "Referrals T+145 to T+155": ("Referrals", 4),
    "Newsletter T+145 to T+155": ("Newsletter", 4),
    "Google T+145 to T+155": ("Google", 4),
    "Overall T+145 to T+155": ("Overall", 4),
    "Meta T+175 to T+185": ("Meta", 5),
    "Referrals T+175 to T+185": ("Referrals", 5),
    "Newsletter T+175 to T+185": ("Newsletter", 5),
    "Google T+175 to T+185": ("Google", 5),
    "Overall T+175 to T+185": ("Overall", 5),
    "Meta T+205 to T+215": ("Meta", 6),
    "Referrals T+205 to T+215": ("Referrals", 6),
    "Newsletter T+205 to T+215": ("Newsletter", 6),
    "Google T+205 to T+215": ("Google", 6),
    "Overall T+205 to T+215": ("Overall", 6),
    "Meta T+235 and on": ("Meta", 7),
    "Referrals T+235 and on": ("Referrals", 7),
    "Newsletter T+235 and on": ("Newsletter", 7),
    "Google T+235 and on": ("Google", 7),
    "Overall T+235 and on": ("Overall", 7),
}

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

def fetch_segment_stats(seg_id):
    r = requests.get(f"{BASE}/publications/{PUB_ID}/segments/{seg_id}",
                     headers=HEADERS)
    r.raise_for_status()
    d = r.json().get("data", {})
    return {
        "subs":           d.get("subscriber_count", 0) or 0,
        "openRate":       round(d.get("open_rate", 0) or 0, 4),
        "CTR":            round(d.get("click_through_rate", 0) or 0, 4),
        "unsubRate":      round(d.get("pct_unsubscribed", 0) or 0, 4),
        "premiumRate":    round(d.get("pct_premium", 0) or 0, 4),
        "referralRate":   round(d.get("pct_referring", 0) or 0, 4),
        "refsPerReferrer": round(d.get("average_referrals_per_referrer", 0) or 0, 2),
    }

def build_time_windows(all_seg_ids):
    # grid[window_index][channel] = stats dict
    grid = [[None]*len(CHANNELS) for _ in WINDOWS]

    for seg_name, seg_id in all_seg_ids.items():
        if seg_name not in SEGMENT_NAMES:
            continue
        channel, wi = SEGMENT_NAMES[seg_name]
        ci = CHANNELS.index(channel)
        print(f"  Fetching {seg_name}...")
        stats = fetch_segment_stats(seg_id)
        is_overall = channel == "Overall"
        grid[wi][ci] = {**stats, "channel": channel, **({"isOverall": True} if is_overall else {})}

    return grid

def build_js(grid):
    lines = ["const timeWindows = ["]
    for wi, (wname, month) in enumerate(WINDOWS):
        lines.append(f'  {{ name: "{wname}", month: {month}, channels: [')
        for ci, channel in enumerate(CHANNELS):
            s = grid[wi][ci]
            if s is None:
                s = {"subs": 0, "openRate": 0, "CTR": 0, "unsubRate": 0,
                     "premiumRate": 0, "referralRate": 0, "refsPerReferrer": 0}
            overall = ", isOverall: true" if channel == "Overall" else ""
            lines.append(
                f'    {{ channel: "{channel}", subs: {s["subs"]}, '
                f'openRate: {s["openRate"]}, CTR: {s["CTR"]}, '
                f'unsubRate: {s["unsubRate"]}, premiumRate: {s["premiumRate"]}, '
                f'referralRate: {s["referralRate"]}, refsPerReferrer: {s["refsPerReferrer"]}{overall} }},'
            )
        lines.append("  ]},")
    lines.append("];")
    return "\n".join(lines)

def update_html(new_js, pull_date):
    with open("index.html", "r") as f:
        html = f.read()

    # Replace timeWindows data block
    html = re.sub(
        r"const timeWindows = \[.*?\];",
        new_js,
        html,
        flags=re.DOTALL
    )

    # Update pull date in header
    html = re.sub(
        r"Data pulled [A-Za-z]+ \d+, \d{4}",
        f"Data pulled {pull_date}",
        html
    )

    with open("index.html", "w") as f:
        f.write(html)

if __name__ == "__main__":
    print("Fetching segments list...")
    all_segs = fetch_all_segments()
    print(f"Found {len(all_segs)} total segments")

    print("Fetching stats for T+ segments...")
    grid = build_time_windows(all_segs)

    print("Building JS data...")
    new_js = build_js(grid)

    pull_date = date.today().strftime("%B %-d, %Y")
    print(f"Updating index.html (date: {pull_date})...")
    update_html(new_js, pull_date)

    print("Done!")
