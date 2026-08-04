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
    # Segment engagement stats are only returned when expand[]=stats is
    # passed; without it every rate silently defaults to 0 (August 2026 run).
    r = requests.get(f"{BASE}/publications/{PUB_ID}/segments/{seg_id}",
                     headers=HEADERS,
                     params={"expand[]": "stats"})
    r.raise_for_status()
    d = r.json().get("data", {})
    stats = d.get("stats") or d.get("metrics") or {}

    def pick(*names, default=0):
        # Field names differ between the documented public API ("stats":
        # clickthrough_rate, unsubscribed_rate, percentage_*) and the app
        # API ("metrics": click_through_rate_verified, pct_*); accept both.
        for n in names:
            v = stats.get(n)
            if v not in (None, ""):
                return v
        return default

    # API returns percentages (49.51); the dashboard stores fractions (0.4951).
    def frac(*names):
        return round((pick(*names) or 0) / 100, 4)

    subs = d.get("total_results", pick("total_subscribers")) or 0
    total_refs = pick("total_referrals")
    referral_rate = frac("percentage_subscribers_with_referrals", "pct_referring")
    refs_per_referrer = pick("average_referrals_per_referrer", default=None)
    if refs_per_referrer is None:
        referrers = subs * referral_rate
        refs_per_referrer = (total_refs / referrers) if referrers else 0
    return {
        "subs":           subs,
        "openRate":       frac("open_rate"),
        "CTR":            frac("click_through_rate_verified", "clickthrough_rate",
                               "click_through_rate"),
        "unsubRate":      frac("unsubscribed_rate", "pct_unsubscribed"),
        "premiumRate":    frac("percentage_premium_subscribers", "pct_premium"),
        "referralRate":   referral_rate,
        "refsPerReferrer": round(refs_per_referrer or 0, 2),
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

def archive_outgoing_pull(html, new_pull_date):
    """Append the current (about-to-be-replaced) timeWindows data to the
    archivedPulls array so past pulls remain as dated rows in the Total LTV
    history table. Idempotent: skips if that pull date is already archived."""
    from datetime import datetime
    date_m = re.search(r"Data pulled ([A-Za-z]+ \d+, \d{4})", html)
    tw_m = re.search(r"const timeWindows = \[(.*?)\];", html, flags=re.DOTALL)
    ap_m = re.search(r"(const archivedPulls = \[.*?)(\n\];)", html, flags=re.DOTALL)
    if not (date_m and tw_m and ap_m):
        print("  NOTE: archivedPulls block or pull date not found; skipping archive")
        return html
    if date_m.group(1) == new_pull_date:
        print("  Outgoing pull has the same date as this run (re-run); skipping archive")
        return html
    label = datetime.strptime(date_m.group(1), "%B %d, %Y").strftime("%b %-d, %Y")
    if f'label: "{label}"' in ap_m.group(1):
        print(f"  Archive for {label} already present; skipping")
        return html
    entry = f'  {{ label: "{label}", windows: [{tw_m.group(1).rstrip()}\n  ] }},\n'
    print(f"  Archiving outgoing pull as '{label}'")
    return html[:ap_m.end(1)] + "\n" + entry.rstrip("\n") + html[ap_m.end(1):]

def update_html(new_js, pull_date):
    with open("index.html", "r") as f:
        html = f.read()
    html = archive_outgoing_pull(html, pull_date)
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

    # Guard against the August 2026 failure mode: subs present but every rate
    # zero (stats not expanded / field names drifted). A populated segment with
    # a genuinely 0% open rate is implausible at this list's scale.
    populated = [cell for row in grid for cell in row if cell and cell["subs"] > 0]
    rateless = [c for c in populated if c["openRate"] == 0]
    if populated and len(rateless) > len(populated) / 2:
        sys.exit(f"ABORT: {len(rateless)}/{len(populated)} populated segments "
                 "returned all-zero rates — stats are missing or field names "
                 "changed; refusing to overwrite the dashboard. (August 2026 "
                 "published zero rates because expand[]=stats was not passed.)")

    print("Building JS data...")
    new_js = build_js(grid)
    pull_date = date.today().strftime("%B %-d, %Y")
    print(f"Updating index.html (date: {pull_date})...")
    update_html(new_js, pull_date)
    print("Done!")
