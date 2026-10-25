"""اختيار فيديو الخلفية (طبيعة / شلالات).

الترتيب:
1) فيديوهات انت حاططها بنفسك في فولدر backgrounds/  (أضمن حاجة – انت اللي مختارها)
   كل فيديو بيتستخدم مرة، ولما يخلصوا بيروح لـ Pexels ويرجع يكررهم بعد فترة
2) Pexels API  (مجاني – محتاج PEXELS_API_KEY)
3) Pixabay API (مجاني – محتاج PIXABAY_API_KEY)
4) لو مفيش أي حاجة: خلفية متدرجة متحركة بتتعمل بـ FFmpeg
الصوت الأصلي لأي فيديو بيتشال تمامًا – مفيش موسيقى.
"""
import os
import random

from .common import CACHE, ROOT, download, http_get, run

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


def _local(used):
    folder = ROOT / "backgrounds"
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in VIDEO_EXT)
    if not files:
        return None
    fresh = [p for p in files if f"local:{p.name}" not in used]
    if not fresh:
        if os.getenv("PEXELS_API_KEY") or os.getenv("PIXABAY_API_KEY"):
            return None  # كل فيديوهاتك اتستخدمت مؤخرًا → هات جديد من Pexels
        fresh = files
    p = random.choice(fresh)
    return p, f"local:{p.name}", "خلفية من مكتبتك"


def _pexels(cfg, min_dur, used):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    queries = cfg["video"]["pexels_queries"][:]
    random.shuffle(queries)
    for q in queries[:4]:
        r = http_get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                     params={"query": q, "orientation": "portrait", "size": "medium", "per_page": 40})
        vids = [v for v in r.json().get("videos", []) if f"pexels:{v['id']}" not in used]
        long_enough = [v for v in vids if v.get("duration", 0) >= min_dur]
        pool = long_enough or vids
        random.shuffle(pool)
        for v in pool:
            files = [f for f in v.get("video_files", [])
                     if f.get("height") and f.get("width") and f["height"] > f["width"] and f["height"] >= 1280
                     and f.get("file_type") == "video/mp4"]
            if not files:
                continue
            f = min(files, key=lambda f: abs(f["height"] - 1920))
            path = download(f["link"], CACHE / "bg" / f"pexels_{v['id']}.mp4")
            credit = f"Pexels – {v.get('user', {}).get('name', '')}".strip(" –")
            return path, f"pexels:{v['id']}", credit
    return None


def _pixabay(cfg, min_dur, used):
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return None
    q = random.choice(cfg["video"]["pexels_queries"])
    r = http_get("https://pixabay.com/api/videos/",
                 params={"key": key, "q": q, "per_page": 50, "safesearch": "true"})
    hits = [h for h in r.json().get("hits", []) if f"pixabay:{h['id']}" not in used]
    hits = [h for h in hits if h.get("duration", 0) >= min_dur] or hits
    if not hits:
        return None
    h = random.choice(hits)
    vids = h["videos"]
    url = (vids.get("large") or {}).get("url") or vids["medium"]["url"]
    path = download(url, CACHE / "bg" / f"pixabay_{h['id']}.mp4")
    return path, f"pixabay:{h['id']}", f"Pixabay – {h.get('user', '')}"


def _generated(cfg, duration):
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    path = CACHE / "bg" / "generated.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"gradients=s={w}x{h}:c0=0x0b3d2e:c1=0x1b5e7a:c2=0x2e7d5b:n=3:speed=0.004:d={duration + 2}:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", str(path)])
    return path, "generated", ""


def get_background(cfg, min_dur, used):
    for fn in (lambda: _local(used), lambda: _pexels(cfg, min_dur, used), lambda: _pixabay(cfg, min_dur, used)):
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            print(f"  background source failed: {type(e).__name__}")
            res = None
        if res:
            return res
    print("  ⚠️  no background source configured – using generated gradient")
    return _generated(cfg, min_dur)

