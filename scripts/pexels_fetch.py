#!/usr/bin/env python3
"""Fetch a real, commercially-licensed photo or video from Pexels for use as an
ad-creative background. Free API (no cost); key from PEXELS_API_KEY env or
~/.secrets/pexels.env. Downloads the best portrait/square match, or lists N
candidates so a human/Claude can pick.

Examples:
  python3 scripts/pexels_fetch.py --type video --query "snowing city night" --orientation portrait --out bg.mp4
  python3 scripts/pexels_fetch.py --type photo --query "calm misty lake sunrise" --orientation square --out bg.jpg
  python3 scripts/pexels_fetch.py --type video --query "city night" --candidates 5      # list, don't download

License note: Pexels content is free for commercial use (incl. paid ads), no
attribution required, modification/crop allowed. Avoid clips with identifiable
people for endorsement-style use; scenery/nature is clean.

Requires python3.12+ (system python3.9 fails Pexels SSL — same gotcha as Meta).
"""
import argparse, json, os, sys, urllib.parse, urllib.request

def pexels_key():
    k = os.environ.get("PEXELS_API_KEY")
    if k:
        return k.strip()
    p = os.path.expanduser("~/.secrets/pexels.env")
    if os.path.exists(p):
        for line in open(p):
            if line.strip().startswith("PEXELS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("No Pexels key: set PEXELS_API_KEY or put it in ~/.secrets/pexels.env")

def api(path, params, key):
    url = f"https://api.pexels.com/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))

# target height by orientation (portrait 9:16, square 1:1, landscape 16:9)
TARGET_H = {"portrait": 1920, "square": 1080, "landscape": 1080}

def rank_video(videos, orient, min_dur):
    out = []
    th = TARGET_H[orient]
    for v in videos:
        files = [f for f in v["video_files"] if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")]
        if orient == "portrait":
            files = [f for f in files if f["height"] > f["width"]]
        elif orient == "landscape":
            files = [f for f in files if f["width"] > f["height"]]
        else:
            files = [f for f in files if abs(f["width"] - f["height"]) < max(f["width"], f["height"]) * 0.2]
        if not files or v.get("duration", 0) < min_dur:
            continue
        files.sort(key=lambda f: (abs(f["height"] - th), -f["width"]))
        f = files[0]
        out.append({"id": v["id"], "duration": v["duration"], "w": f["width"], "h": f["height"],
                    "link": f["link"], "src_page": v.get("url")})
    out.sort(key=lambda c: (abs(c["h"] - th), -c["w"]))
    return out

def rank_photo(photos, orient):
    th = TARGET_H[orient]
    out = []
    for ph in photos:
        w, h = ph["width"], ph["height"]
        if w < 1080 or h < 1080:
            continue
        out.append({"id": ph["id"], "w": w, "h": h, "link": ph["src"]["large2x"], "src_page": ph.get("url")})
    out.sort(key=lambda c: abs(c["h"] - th))
    return out

def download(url, out):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=180).read()
    open(out, "wb").write(data)
    return len(data)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["photo", "video"], required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--orientation", default="portrait", choices=["portrait", "square", "landscape"])
    ap.add_argument("--min-duration", type=int, default=6, help="video only: min seconds")
    ap.add_argument("--out", default=None, help="download path; omit with --candidates to just list")
    ap.add_argument("--candidates", type=int, default=0, help="list top N candidates instead of downloading")
    ap.add_argument("--index", type=int, default=0, help="which ranked candidate to download (0=best)")
    ap.add_argument("--per-page", type=int, default=20)
    a = ap.parse_args()
    key = pexels_key()

    if a.type == "video":
        d = api("videos/search", {"query": a.query, "orientation": a.orientation, "size": "medium", "per_page": a.per_page}, key)
        ranked = rank_video(d.get("videos", []), a.orientation, a.min_duration)
    else:
        d = api("v1/search", {"query": a.query, "orientation": a.orientation, "per_page": a.per_page}, key)
        ranked = rank_photo(d.get("photos", []), a.orientation)

    if not ranked:
        sys.exit(f"No suitable {a.type} for query '{a.query}' ({a.orientation})")

    if a.candidates:
        print(json.dumps([{k: v for k, v in c.items() if k != "link"} for c in ranked[:a.candidates]], indent=1))
        return

    pick = ranked[min(a.index, len(ranked) - 1)]
    if not a.out:
        sys.exit("--out required to download (or use --candidates to list)")
    n = download(pick["link"], a.out)
    print(json.dumps({"picked": {k: v for k, v in pick.items() if k != "link"},
                      "out": a.out, "bytes": n}, indent=1))

if __name__ == "__main__":
    main()
