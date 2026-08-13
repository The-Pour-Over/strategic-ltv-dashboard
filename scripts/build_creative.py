#!/usr/bin/env python3
"""Build a finished TPO ad creative (static JPG or motion MP4) from a JSON spec,
using a real background (Pexels photo/video via pexels_fetch.py) plus our text
overlay. Two proven recipes:

  - font_style "handwritten": Shadows-Into-Light handwritten copy, dark text on a
    warm veil (the sunrise/lake testimonial statics).
  - font_style "boldsans": heavy white sans over a dark scrim (the snow-city
    motion winner).

Motion pipeline: render the text as frames in headless Chrome (deterministic
freeze via negative animation-delay), then:
  - background type "video": composite the transparent text over the real clip (ffmpeg overlay).
  - background type "image": ken-burns the still + bake text, frames -> mp4.
Static pipeline: one Chrome screenshot of bg + text -> jpg.

hook_instant=true renders the FIRST stanza fully on-screen at t=0 (visible the
instant someone swipes to it); the rest reveal on a quick stagger.

Usage:
  python3 scripts/build_creative.py --spec spec.json
  python3 scripts/build_creative.py --spec spec.json --out /path/out.mp4

Requires python3.12+ (SSL), headless Chrome, and ffmpeg on PATH.
Spec schema (JSON):
  {
    "name": "snowcity_recreate",
    "format": "9:16" | "1:1" | "4:5",
    "media": "motion" | "static",
    "font_style": "boldsans" | "handwritten",
    "scrim": "dark" | "warm_veil" | "none",
    "background": {"type": "video"|"image", "path": "abs/or/rel/path"},
    "stanzas": ["...first (hook)...", "...", "..."],
    "hook_instant": true,
    "duration": 6, "fps": 15,
    "out": "action-center/data/built_x.mp4"
  }
"""
import argparse, json, os, subprocess, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(REPO, "action-center", "fonts")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DIMS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
# stagger schedule (start%, full%) for stanzas 1..n when NOT hook_instant-frozen
SCHED = [(0, 7), (13, 22), (27, 37), (43, 53), (57, 67), (70, 80)]


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("'", "&rsquo;").replace('"', "&rdquo;"))


def font_css(style):
    if style == "handwritten":
        return f"""
      @font-face {{ font-family:"AdHand"; src:url("{FONTS}/ShadowsIntoLightTwo.woff2"); }}
      @font-face {{ font-family:"AdHand"; src:url("{FONTS}/Schoolbell.woff2"); unicode-range:U+49; }}
      .copy {{ font-family:"AdHand",cursive; color:#3d3428;
               text-shadow:0 0 18px rgba(255,248,235,.55); }}
      .hook {{ font-size:54px; line-height:1.28; margin-bottom:36px; }}
      .stanza {{ font-size:44px; line-height:1.42; margin-bottom:32px; }}
      .stanza:last-child {{ margin-bottom:0; }}"""
    return """
      .copy { font-family:"Helvetica Neue",Arial,sans-serif; font-weight:800; color:#fff;
              text-shadow:0 2px 16px rgba(0,0,0,.9),0 0 4px rgba(0,0,0,.7); }
      .hook, .stanza { font-size:62px; line-height:1.22; margin-bottom:52px; }
      .stanza:last-child { margin-bottom:0; }"""


def scrim_css(kind):
    if kind == "warm_veil":
        return ".scrim{position:absolute;inset:0;background:rgba(255,248,235,.30);}"
    if kind == "dark":
        return (".scrim{position:absolute;inset:0;background:linear-gradient(180deg,"
                "rgba(5,7,13,.42) 0%,rgba(5,7,13,.30) 24%,rgba(5,7,13,.34) 50%,"
                "rgba(5,7,13,.50) 74%,rgba(5,7,13,.80) 100%);}")
    return ".scrim{display:none;}"


def keyframes(n, hook_instant, dur):
    out = []
    for i in range(n):
        if i == 0 and hook_instant:
            out.append(f"@keyframes r{i}{{0%,100%{{opacity:1;transform:none}}}}")
        else:
            s, f = SCHED[i] if i < len(SCHED) else (min(85, 43 + i * 12), min(95, 53 + i * 12))
            out.append(f"@keyframes r{i}{{0%,{s}%{{opacity:0;transform:translateY(22px)}}"
                       f"{f}%,100%{{opacity:1;transform:none}}}}")
    anim = "".join(
        f".x{i}{{animation-name:r{i};animation-duration:{dur}s;"
        f"animation-timing-function:cubic-bezier(.2,.7,.2,1);"
        f"animation-delay:calc(-1*var(--t));animation-play-state:paused;animation-fill-mode:both;}}"
        for i in range(n))
    return "\n".join(out) + "\n" + anim


def html(spec, W, H, baked_bg=None):
    style = spec["font_style"]
    stanzas = spec["stanzas"]
    n = len(stanzas)
    dur = spec.get("duration", 6)
    kb = ("img.bg{position:absolute;inset:-6%;width:112%;height:112%;object-fit:cover;"
          "transform-origin:55% 55%;animation:kb __DUR__s linear;"
          "animation-delay:calc(-1*var(--t));animation-play-state:paused;animation-fill-mode:both;}"
          "@keyframes kb{from{transform:scale(1.0)}to{transform:scale(1.09) translate(-1.5%,-1%)}}"
          ).replace("__DUR__", str(dur))
    bg_tag = f'<img class="bg" src="{baked_bg}">' if baked_bg else ""
    rows = []
    for i, s in enumerate(stanzas):
        cls = "hook" if (i == 0 and style == "handwritten") else "stanza"
        rows.append(f'<div class="{cls} x{i}">{esc(s)}</div>')
    # opaque body only when the background is baked into the HTML (image/static);
    # overlay mode (motion over video) MUST stay transparent so the footage shows through
    body_bg = "#05070d" if baked_bg else "transparent"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;background:{body_bg};overflow:hidden}}
:root{{--t:0s}}
.stage{{position:relative;width:{W}px;height:{H}px;overflow:hidden}}
{kb if baked_bg else ""}
{scrim_css(spec.get("scrim","none"))}
.copy{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
justify-content:center;text-align:center;padding:0 {88 if W>=1080 and H>1400 else 90}px}}
{font_css(style)}
{keyframes(n, spec.get("hook_instant", False), dur)}
</style></head><body><div class="stage">
{bg_tag}<div class="scrim"></div><div class="copy">
{''.join(rows)}
</div></div>
<script>var t=parseFloat(new URLSearchParams(location.search).get('t')||'0');
document.documentElement.style.setProperty('--t',t+'s');</script>
</body></html>"""


def render_frame(html_path, W, H, t, out_png, transparent):
    cmd = [CHROME, "--headless=new", f"--window-size={W},{H}", f"--screenshot={out_png}"]
    if transparent:
        cmd.insert(3, "--default-background-color=00000000")
    cmd.append(f"file://{html_path}?t={t}")
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", default=None, help="override spec.out")
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    W, H = DIMS[spec["format"]]
    out = a.out or spec["out"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bg = spec.get("background", {})
    tmp = tempfile.mkdtemp(prefix="crtv_")

    # ---- STATIC ----
    if spec["media"] == "static":
        assert bg.get("type") == "image", "static needs an image background"
        hp = os.path.join(tmp, "s.html")
        open(hp, "w").write(html(spec, W, H, baked_bg=os.path.abspath(bg["path"])))
        png = os.path.join(tmp, "s.png")
        render_frame(hp, W, H, 0, png, transparent=False)
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", png, "--out", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"built static {out}")
        return

    # ---- MOTION ----
    dur, fps = spec.get("duration", 6), spec.get("fps", 15)
    N = dur * fps
    over_video = bg.get("type") == "video"
    hp = os.path.join(tmp, "m.html")
    open(hp, "w").write(html(spec, W, H, baked_bg=None if over_video else os.path.abspath(bg["path"])))
    for i in range(N):
        render_frame(hp, W, H, i / fps, os.path.join(tmp, f"f_{i:04d}.png"), transparent=over_video)

    if over_video:
        st = float(bg.get("start", 0))  # start offset into the clip (skip dark fade-in)
        fc = (f"[0:v]trim={st}:{st + dur},setpts=PTS-STARTPTS,"
              f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[bg];"
              f"[1:v]fps=30,format=rgba[tx];[bg][tx]overlay=0:0:format=auto,format=yuv420p[out]")
        cmd = ["ffmpeg", "-y", "-i", os.path.abspath(bg["path"]),
               "-framerate", str(fps), "-i", os.path.join(tmp, "f_%04d.png"),
               "-filter_complex", fc, "-map", "[out]", "-t", str(dur),
               "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-movflags", "+faststart", out]
    else:
        cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", os.path.join(tmp, "f_%04d.png"),
               "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
               "-vf", f"scale={W}:{H}:flags=lanczos", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + "\n".join(r.stderr.splitlines()[-4:]))
    print(f"built motion {out}")


if __name__ == "__main__":
    main()
