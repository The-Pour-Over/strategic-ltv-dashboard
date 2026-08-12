#!/usr/bin/env python3
"""Regenerate client/public/data/adset_status.json from the live Meta API.

The Hub's "Live tests" section trusts this file for which ad sets are ACTIVE
right now — run this alongside creative_metrics.py on every artifact refresh,
or the active/paused badges go stale.

Usage: python3 scripts/adset_status.py [--data <dir>]
Creds: META_ADS_TOKEN env var, or ~/.secrets/meta-ads.env (never hardcoded).
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import meta_creds, resolve_data_dir

_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=None, help="output dir (default: auto-detect action-center/data or client/public/data)")
_args = _ap.parse_args()

ACCOUNT = "act_125820816056365"  # TPO I: Secondary
TOKEN, VER = meta_creds()
OUT = os.path.join(resolve_data_dir(_args.data), "adset_status.json")

params = {
    "fields": "name,effective_status",
    "limit": "200",
    "access_token": TOKEN,
}
url = f"https://graph.facebook.com/{VER}/{ACCOUNT}/adsets?" + urllib.parse.urlencode(params)

active = {}
pages = 0
while url and pages < 10:
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    for row in data.get("data", []):
        if row.get("effective_status") == "ACTIVE":
            active[row["name"]] = "ACTIVE"
    url = data.get("paging", {}).get("next")
    pages += 1

out = {"as_of": datetime.date.today().isoformat(), "active": active}
json.dump(out, open(OUT, "w"), indent=1)
print(f"wrote {len(active)} ACTIVE ad sets -> {OUT}")
