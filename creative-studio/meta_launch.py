#!/usr/bin/env python3
"""Create PAUSED Meta objects for an approved creative, following the proven
TPO paid-ads LAUNCH_PLAYBOOK spec exactly. An isolated PAUSED test campaign so
nothing touches the live Qualified Lead structure. Everything PAUSED — a human
does the Advantage+ creative AI-off pass (§4b) and activates in Ads Manager.

Graph-friendly: no reference reads (proven config is hardcoded per the playbook),
campaign + ad set created ONCE and cached, every call paced >=2s. The only poll
loop is waiting for video processing (paced, capped).

Creds: ~/.secrets/meta-ads.env. Run with python3.12 (SSL).
"""
import json, os, subprocess, time, urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, ".meta_state.json")
GRAPH = "https://graph.facebook.com/v23.0"

# ---- proven constants (paid-ads/LAUNCH_PLAYBOOK.md, verified 2026-06-23) ----
PIXEL_ID = "789006421963427"
PROMOTED_OBJECT = {"pixel_id": PIXEL_ID, "custom_event_type": "LEAD"}
EXCLUDE_AUDIENCE = "120249064164790224"       # "180 day sign up, always exclude" — MANDATORY
TARGETING = {"geo_locations": {"countries": ["US"]}, "age_min": 18,
             "excluded_custom_audiences": [{"id": EXCLUDE_AUDIENCE}],
             "targeting_automation": {"advantage_audience": 1}}  # adv+ broad
OPT_GOAL = "OFFSITE_CONVERSIONS"
BILLING_EVENT = "IMPRESSIONS"
BID_STRATEGY = "LOWEST_COST_WITHOUT_CAP"      # "Highest volume"
DESTINATION = "WEBSITE"
DAILY_BUDGET_CENTS = 20000                    # $200/day new-test standard (PAUSED anyway)
LINK_URL = "https://www.thepourover.org/"
HEADLINE = "Read the news in 5 min — free, Christ-first."
DESCRIPTION = "Faithful news here."
URL_TAGS = "utm_source=facebookads&utm_medium={{adset.name}}&utm_campaign={{ad.name}}"  # MANDATORY §5b
CTA_TYPE = "SIGN_UP"
CAMPAIGN_NAME = "AI Creative Test (PAUSED)"
ADSET_NAME = "test_ai_creative_studio_adv+"

_last = [0.0]
def _pace():
    dt = time.time() - _last[0]
    if dt < 2.0:
        time.sleep(2.0 - dt)
    _last[0] = time.time()

def creds():
    env = {}
    for line in open(os.path.expanduser("~/.secrets/meta-ads.env")):
        line = line.strip()
        if line.startswith("export "): line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    acct = env.get("META_AD_ACCOUNT", "").replace("act_", "")
    return env.get("META_ADS_TOKEN"), f"act_{acct}", env.get("META_PAGE_ID")

TOKEN, ACCT, PAGE_ID = creds()

def _get(path, params):
    _pace()
    params = dict(params); params["access_token"] = TOKEN
    with urllib.request.urlopen(f"{GRAPH}/{path}?" + urllib.parse.urlencode(params), timeout=60) as r:
        return json.load(r)

def _post(path, params):
    _pace()
    params = dict(params); params["access_token"] = TOKEN
    req = urllib.request.Request(f"{GRAPH}/{path}", data=urllib.parse.urlencode(params).encode())
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta {e.code}: {e.read().decode()[:400]}")

def _upload(path, endpoint, field):
    _pace()
    r = subprocess.run(["curl", "-sS", f"{GRAPH}/{ACCT}/{endpoint}",
                        "-F", f"access_token={TOKEN}", "-F", f"{field}=@{os.path.abspath(path)}"],
                       capture_output=True, text=True, timeout=300)
    try:
        j = json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f"upload failed: {r.stdout[:200]} {r.stderr[:200]}")
    if "error" in j:
        raise RuntimeError(f"upload error: {j['error'].get('message')}")
    return j

def _state(): return json.load(open(STATE)) if os.path.exists(STATE) else {}
def _save(s): json.dump(s, open(STATE, "w"), indent=2)

def ensure_campaign():
    s = _state()
    if s.get("campaign_id"): return s["campaign_id"]
    r = _post(f"{ACCT}/campaigns", {"name": CAMPAIGN_NAME, "objective": "OUTCOME_LEADS",
                                    "status": "PAUSED", "special_ad_categories": "[]"})
    s["campaign_id"] = r["id"]; _save(s); return r["id"]

def ensure_adset():
    s = _state()
    if s.get("adset_id"): return s["adset_id"]
    r = _post(f"{ACCT}/adsets", {
        "name": ADSET_NAME, "campaign_id": ensure_campaign(), "status": "PAUSED",
        "daily_budget": str(DAILY_BUDGET_CENTS), "billing_event": BILLING_EVENT,
        "optimization_goal": OPT_GOAL, "bid_strategy": BID_STRATEGY,
        "destination_type": DESTINATION, "is_dynamic_creative": "false",
        "promoted_object": json.dumps(PROMOTED_OBJECT), "targeting": json.dumps(TARGETING)})
    s["adset_id"] = r["id"]; _save(s); return r["id"]

def _creative_image(path, message):
    up = _upload(path, "adimages", "source")
    h = list(up["images"].values())[0]["hash"]
    story = {"page_id": PAGE_ID, "link_data": {
        "image_hash": h, "link": LINK_URL, "message": message, "name": HEADLINE,
        "description": DESCRIPTION,
        "call_to_action": {"type": CTA_TYPE, "value": {"link": LINK_URL}}}}
    return _post(f"{ACCT}/adcreatives", {"name": "studio_img_creative",
                 "object_story_spec": json.dumps(story), "url_tags": URL_TAGS})["id"]

def _creative_video(path, message):
    vid = _upload(path, "advideos", "source")["id"]
    thumb = None
    for _ in range(20):                       # wait for processing (paced, capped)
        time.sleep(6)
        st = _get(vid, {"fields": "status,thumbnails"})
        if st.get("status", {}).get("video_status") == "ready":
            th = (st.get("thumbnails") or {}).get("data") or []
            thumb = th[0]["uri"] if th else None
            break
    vd = {"video_id": vid, "message": message, "title": HEADLINE,
          "link_description": DESCRIPTION,
          "call_to_action": {"type": CTA_TYPE, "value": {"link": LINK_URL}}}
    if thumb: vd["image_url"] = thumb
    story = {"page_id": PAGE_ID, "video_data": vd}
    return _post(f"{ACCT}/adcreatives", {"name": "studio_vid_creative",
                 "object_story_spec": json.dumps(story), "url_tags": URL_TAGS})["id"]

def launch(item):
    """item: {name, media ('motion'|'static'), path, message}. Returns ids + notes."""
    adset_id = ensure_adset()
    cid = (_creative_video if item["media"] == "motion" else _creative_image)(item["path"], item.get("message", ""))
    ad = _post(f"{ACCT}/ads", {"name": item["name"][:60] + " (PAUSED)", "adset_id": adset_id,
               "creative": json.dumps({"creative_id": cid}), "status": "PAUSED"})
    st = _state()
    return {"campaign_id": st.get("campaign_id"), "adset_id": adset_id,
            "creative_id": cid, "ad_id": ad["id"],
            "note": "PAUSED. Do the Advantage+ creative AI-off pass in Ads Manager (playbook §4b), then activate."}

if __name__ == "__main__":
    import sys
    print(json.dumps(launch(json.loads(sys.argv[1])), indent=2))
