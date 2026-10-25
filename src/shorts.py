"""فيديو قصير يومي (دعاء أو حديث) لتيك توك ويوتيوب شورتس بس – نفس محتوى البوستات المتراجع (data/posts.json).

النص بيظهر سطر سطر بهدوء على خلفية طبيعة متحركة مع صوت هادي (مفيش موسيقى ولا صوت مولَّد).
  python -m src.shorts                                   # يولّد بدون نشر
  python -m src.shorts --publish                         # ينشر على تيك توك ويوتيوب
  python -m src.shorts --publish --platforms youtube
"""
import argparse
import datetime as dt
import json
import random
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import posts
from .backgrounds import get_background
from .common import DATA, ROOT, ar_num, load_json, media_duration, run, save_json
from .render import GOLD, UI_BOLD, UI_FONT, QURAN_FONT, _font, compose

OUT = ROOT / "out_short"
HISTORY = ROOT / "shorts_history.json"
W, H = 1080, 1920
PLATFORMS = ("tiktok", "youtube")


def pick(history, posts_history):
    items = load_json(DATA / "posts.json")["items"]
    now = dt.datetime.now(dt.timezone.utc)

    def recent(h, days):
        return {p["id"] for p in h["posts"] if now - dt.datetime.fromisoformat(p["date"]) < dt.timedelta(days=days)}
    used = recent(history, 90) | recent(posts_history, 10)  # مش نفس بوست الأيام اللي فاتت
    last = history["posts"][-1]["type"] if history["posts"] else None
    fresh = [i for i in items if i["id"] not in used] or items
    prefer = [i for i in fresh if (i["type"] == "hadith") != (last == "hadith")] or fresh
    return random.choice(prefer)


def _wrap(text, font, max_w):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if not cur or font.getlength(t, direction="rtl") <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


class LinesTimeline:
    """The panel fades in, then each line fades in one after another."""

    def __init__(self, base, lines, times, total):
        self.base, self.lines, self.times, self.total = base, lines, times, total

    def _a(self, t):
        return min(1.0, t / 0.6, max(0.0, (self.total - t) / 0.8))

    def state(self, t):
        a = round(self._a(t), 2)
        ops = [("b", a)]
        for k, s in enumerate(self.times):
            p = round(min(1.0, max(0.0, (t - s) / 0.7)), 2)
            if p > 0:
                ops.append((k, round(p * a, 2)))
        return tuple(ops)

    @staticmethod
    def _alpha(img, m):
        if m >= 1:
            return img
        arr = np.array(img)
        arr[..., 3] = (arr[..., 3].astype(np.float32) * m).astype(np.uint8)
        return Image.fromarray(arr, "RGBA")

    def render(self, ops, W_, H_):
        c = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        for k, m in ops:
            c.alpha_composite(self._alpha(self.base if k == "b" else self.lines[k], m))
        return c


def build(item, text, src):
    is_quran = item["type"] in ("quran_dua", "quran")
    fpath = QURAN_FONT if is_quran else UI_BOLD
    size = 76
    while True:
        f = _font(fpath, size)
        lines = _wrap(text, f, W - 200)
        lh = int(size * (1.95 if is_quran else 1.75))
        if len(lines) * lh <= H * 0.40 or size <= 38:
            break
        size -= 2
    pre = item.get("pre") or ("قال رسول الله ﷺ:" if item["type"] == "hadith" else "")
    title = item.get("title") or posts.TITLES[item["type"]]
    f_title, f_pre, f_src = _font(UI_BOLD, 54), _font(UI_FONT, 44), _font(UI_FONT, 40)
    block = 100 + (76 if pre else 0) + len(lines) * lh + 44 + 60
    top = int(H * 0.45) - block // 2
    cx = W // 2

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((58, top - 60, W - 58, top + block + 52), radius=48,
                                            fill=(0, 0, 0, 150))
    base = panel.filter(ImageFilter.GaussianBlur(18))
    d = ImageDraw.Draw(base)
    y = top
    d.text((cx, y + 30), title, font=f_title, fill=GOLD, anchor="mm", direction="rtl")
    y += 76
    d.line((cx - 130, y, cx + 130, y), fill=GOLD[:3] + (160,), width=2)
    y += 24
    if pre:
        d.text((cx, y + 30), pre, font=f_pre, fill=(255, 255, 255, 220), anchor="mm", direction="rtl")
        y += 76
    first = y
    y += len(lines) * lh + 44
    d.text((cx, y), src, font=f_src, fill=GOLD, anchor="mm", direction="rtl")
    d.text((cx, H - 300), "سَكينة يومية", font=_font(UI_BOLD, 42), fill=(255, 255, 255, 190), anchor="mm",
           direction="rtl")

    layers = []
    for k, ln in enumerate(lines):
        cy = first + k * lh + lh // 2
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((cx + 3, cy + 4), ln, font=f, fill=(0, 0, 0, 180), anchor="mm", direction="rtl")
        layer = layer.filter(ImageFilter.GaussianBlur(5))
        ImageDraw.Draw(layer).text((cx, cy), ln, font=f, fill=(255, 255, 255, 255), anchor="mm", direction="rtl")
        layers.append(layer)
    n_words = len(text.split())
    total = max(12.0, min(40.0, 6.0 + n_words / 1.6))
    step = min(2.2, (total * 0.55) / max(1, len(layers)))
    times = [1.0 + k * step for k in range(len(layers))]
    return LinesTimeline(base, layers, times, total), total


def ambient(dest, total):
    amb = (f"anoisesrc=color=brown:amplitude=0.5:duration={total:.2f}:sample_rate=44100,"
           f"lowpass=f=700,highpass=f=50,volume='0.55+0.35*sin(2*PI*t/8.5)':eval=frame,"
           f"afade=t=in:d=1.5,afade=t=out:st={max(0.1, total - 2):.2f}:d=2,volume=0.35,loudnorm=I=-24")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", amb, "-ac", "2", "-ar", "44100",
         "-t", f"{total:.2f}", str(dest)])
    return dest


def captions(item, text, src):
    t = item["type"]
    opener = random.choice(posts.OPENERS[t])
    cta = random.choice(posts.DUA_CTAS if t in ("dua", "quran_dua") else posts.CTAS)
    tags = posts.HASHTAGS[t]
    pre = item.get("pre") or ("قال رسول الله ﷺ:" if t == "hadith" else "")
    body = f"{opener}\n\n{pre + chr(10) if pre else ''}{text}\n\n📚 {src}\n\n{cta}"
    title = f"{opener.rstrip(' 🤍🤲')} | {posts.TITLES[t]} #shorts"
    return {"tiktok": f"{body}\n{' '.join(tags + ['#fyp'])}"[:2200],
            "youtube": f"{body}\n\nتابع سَكينة يومية لتذكير يومي 🤍\n\n{' '.join(tags[:4] + ['#shorts'])}",
            "_yt_title": title[:100], "_yt_tags": ["سكينة يومية", posts.TITLES[t], "دعاء", "حديث شريف", "اسلاميات"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--platforms", default="")
    args = ap.parse_args()
    cfg = load_json(ROOT / "config.json")
    history = load_json(HISTORY) if HISTORY.exists() else {"posts": []}
    ph = ROOT / "posts_history.json"
    posts_history = load_json(ph) if ph.exists() else {"posts": []}
    for p in posts_history["posts"]:
        p.setdefault("date", "2000-01-01T00:00:00+00:00")

    item = pick(history, posts_history)
    text, src = posts.item_text(item)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    tl, total = build(item, text, src)
    audio = ambient(OUT / "audio.wav", total)
    bg, bg_id, _ = get_background(cfg, total, {p.get("background") for p in history["posts"][-40:]})
    v = cfg["video"]
    reel = compose(background=bg, timeline=tl, audio=audio, total=total, dest=OUT / "reel.mp4",
                   W=W, H=H, fps=v.get("fps", 30), darken=v.get("background_darken", 0.3))
    caps = captions(item, text, src)
    for k, c in caps.items():
        (OUT / f"caption{k if k.startswith('_') else '_' + k}.txt").write_text(
            c if isinstance(c, str) else json.dumps(c, ensure_ascii=False), encoding="utf-8")
    print(f"🎬 {item['id']} ({item['type']}) {media_duration(reel):.1f}s\n\n{caps['tiktok']}")
    if not args.publish:
        return

    platforms = [p for p in (args.platforms.split(",") if args.platforms else PLATFORMS)
                 if p in PLATFORMS and cfg["platforms"].get(p, {}).get("enabled")]
    results = {}
    for name in platforms:
        try:
            if name == "youtube":
                from .publish_youtube import publish_youtube
                results[name] = {"ok": True, **publish_youtube(cfg, reel, caps["youtube"], caps["_yt_title"],
                                                               caps["_yt_tags"])}
            else:
                from .publish_tiktok import publish_tiktok
                results[name] = {"ok": True, **publish_tiktok(cfg, reel, caps["tiktok"])}
        except Exception as e:  # noqa: BLE001
            results[name] = {"ok": False, "error": type(e).__name__}
        print(f"   {name}: {results[name]}")
    history["posts"].append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                             "id": item["id"], "type": item["type"], "background": bg_id, "results": results})
    save_json(HISTORY, history)
    if results and not any(r["ok"] for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()

