#!/usr/bin/env python3
"""Creative Studio — local test harness for the AI ad pipeline.

  "Make 5 ad creatives"  -> generate 3 motion + 2 static from the analyzer's top
                            gaps, with REAL Pexels backgrounds (build_creative.py)
  gallery                -> watch them render, then play each
  green "Approve"        -> create a PAUSED ad set + ad in an isolated test
                            campaign on Meta (meta_launch.py); you finish in Ads Manager

Run:  python3.12 creative-studio/app.py   ->  http://localhost:8765
Zero dependencies (stdlib only). Generation runs in a background thread.
"""
import json, os, sys, threading, subprocess, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "scripts")
GEN = os.path.join(HERE, "generated")
PY = sys.executable  # launch this app with python3.12 so subprocesses inherit it
os.makedirs(GEN, exist_ok=True)

BRIEFS = json.load(open(os.path.join(HERE, "briefs.json")))
LOCK = threading.Lock()
STATE = {b["id"]: {"id": b["id"], "gap": b["gap"], "media": b["media"],
                   "format": b["format"], "status": "idle", "url": None, "error": None}
         for b in BRIEFS}
GENERATING = {"on": False}

# rehydrate: any creatives already rendered on disk survive a server restart
for _b in BRIEFS:
    _ext = "mp4" if _b["media"] == "motion" else "jpg"
    _fp = os.path.join(GEN, f"built_{_b['id']}.{_ext}")
    if os.path.exists(_fp):
        STATE[_b["id"]].update(status="done", url=f"/media/built_{_b['id']}.{_ext}")

def _set(bid, **kw):
    with LOCK:
        STATE[bid].update(kw)

def generate_one(b):
    bid = b["id"]
    _set(bid, status="generating", error=None, url=None)
    try:
        ext_bg = "mp4" if b["pexels"]["type"] == "video" else "jpg"
        bg = os.path.join(GEN, f"bg_{bid}.{ext_bg}")
        pf = subprocess.run([PY, os.path.join(SCRIPTS, "pexels_fetch.py"),
                             "--type", b["pexels"]["type"], "--query", b["pexels"]["query"],
                             "--orientation", b["pexels"]["orientation"],
                             "--index", str(b["pexels"].get("index", 0)), "--out", bg],
                            capture_output=True, text=True)
        if pf.returncode != 0:
            raise RuntimeError("pexels: " + (pf.stderr or pf.stdout).strip().splitlines()[-1])
        out_ext = "mp4" if b["media"] == "motion" else "jpg"
        out = os.path.join(GEN, f"built_{bid}.{out_ext}")
        spec = {"name": bid, "format": b["format"], "media": b["media"],
                "font_style": b["font_style"], "scrim": b["scrim"],
                "background": {"type": "video" if b["pexels"]["type"] == "video" else "image",
                               "path": bg},
                "stanzas": b["stanzas"], "hook_instant": b.get("hook_instant", False),
                "duration": b.get("duration", 6), "fps": b.get("fps", 15), "out": out}
        if b.get("music"):
            m = dict(b["music"])
            m["path"] = os.path.join(REPO, m["path"])  # briefs store repo-relative paths
            spec["music"] = m
        sp = os.path.join(GEN, f"spec_{bid}.json")
        json.dump(spec, open(sp, "w"))
        bc = subprocess.run([PY, os.path.join(SCRIPTS, "build_creative.py"), "--spec", sp],
                            capture_output=True, text=True)
        if bc.returncode != 0:
            raise RuntimeError("build: " + (bc.stderr or bc.stdout).strip().splitlines()[-1])
        _set(bid, status="done", url=f"/media/built_{bid}.{out_ext}")
    except Exception as e:
        _set(bid, status="error", error=str(e))

def generate_all():
    GENERATING["on"] = True
    try:
        for b in BRIEFS:
            generate_one(b)
    finally:
        GENERATING["on"] = False

def approve(bid):
    b = next(x for x in BRIEFS if x["id"] == bid)
    out_ext = "mp4" if b["media"] == "motion" else "jpg"
    path = os.path.join(GEN, f"built_{bid}.{out_ext}")
    if not os.path.exists(path):
        return {"ok": False, "error": "creative not built yet"}
    import importlib.util
    spec = importlib.util.spec_from_file_location("meta_launch", os.path.join(HERE, "meta_launch.py"))
    ml = importlib.util.module_from_spec(spec); spec.loader.exec_module(ml)
    try:
        ids = ml.launch({"name": bid + "_" + b["gap"][:24], "media": b["media"],
                         "path": path, "message": b["stanzas"][0]})
        return {"ok": True, "ids": ids}
    except Exception as e:
        return {"ok": False, "error": str(e)}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/" or p == "/index.html":
            return self._send(200, open(os.path.join(HERE, "index.html")).read(), "text/html")
        if p == "/status":
            with LOCK:
                return self._send(200, {"items": list(STATE.values()), "generating": GENERATING["on"]})
        if p.startswith("/media/"):
            fp = os.path.join(GEN, os.path.basename(p))
            if not os.path.exists(fp):
                return self._send(404, {"error": "not found"})
            ct = "video/mp4" if fp.endswith(".mp4") else "image/jpeg"
            size = os.path.getsize(fp)
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                try:
                    a, _, b = rng.split("=", 1)[1].partition("-")
                    start = int(a) if a else 0
                    end = int(b) if b else size - 1
                except Exception:
                    start, end = 0, size - 1
                start = max(0, start); end = min(end, size - 1)
                length = max(0, end - start + 1)
                with open(fp, "rb") as f:
                    f.seek(start); chunk = f.read(length)
                self.send_response(206)
                self.send_header("Content-Type", ct)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): pass
                return
            with open(fp, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass
            return
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if p == "/make":
            if GENERATING["on"]:
                return self._send(409, {"error": "already generating"})
            threading.Thread(target=generate_all, daemon=True).start()
            return self._send(200, {"started": True})
        if p == "/approve":
            return self._send(200, approve(body.get("id")))
        return self._send(404, {"error": "not found"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    print(f"Creative Studio -> http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
