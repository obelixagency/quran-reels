"""Daily Serenity – morning / evening adhkar stories (1080×1920, English only) on Facebook + Instagram.

Items from data/en/adhkar.json: Sahih al-Bukhari / Sahih Muslim only, plus Ayat al-Kursi (Pickthall).
Rotates so the least-recently shown adhkar come first (3 stories per session).
  python -m src.en.adhkar --session morning            # render only
  python -m src.en.adhkar --session evening --publish
"""
import argparse
import datetime as dt
import shutil
import sys

from PIL import Image, ImageDraw, ImageFilter

from ..common import DATA, ROOT, load_json, save_json
from ..posts import _bg, background_photo
from .video import BEIGE, GOLD_L, W, H, _spaced, _wrap, sans, serif

OUT = ROOT / "out_en_adhkar"
HISTORY = ROOT / "adhkar_history_en.json"
HEAD = {"morning": "Morning Adhkar", "evening": "Evening Adhkar"}


def pick(session, history, n=3):
    items = [i for i in load_json(DATA / "en" / "adhkar.json")["items"] if i["session"] in (session, "both")]
    last = {}
    for k, h in enumerate(history["sessions"]):
        for i in h["ids"]:
            last[i] = k
    items.sort(key=lambda i: last.get(i["id"], -1))
    quran = [i for i in items if i["kind"] == "quran"][:1]
    dhikr = [i for i in items if i["kind"] != "quran"][:max(0, n - len(quran))]
    return quran + dhikr


def render(item, session, idx, total, bg_path, dest):
    img = _bg(bg_path, W, H, 0.5).filter(ImageFilter.GaussianBlur(3)).convert("RGBA")
    words = item["en"].split()
    max_w, max_h = W - 220, 860
    size = 72
    while True:
        f = serif(size)
        lines = [" ".join(l) for l in _wrap(words, f, max_w)]
        lh = int(size * 1.36)
        if len(lines) * lh <= max_h or size <= 36:
            break
        size -= 2
    f_title, f_ref, f_small, f_count = sans(34, 500), sans(34, 420), sans(26, 380), sans(34, 500)
    block = 90 + len(lines) * lh + 40 + (90 if item.get("count") else 0) + 60 + 40
    top = max(460, (H - block) // 2 + 60)

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((64, top - 60, W - 64, top + block + 50), radius=46,
                                            fill=(20, 28, 24, 160))
    img = Image.alpha_composite(img, panel.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    cx = W // 2
    d.text((cx, 250), HEAD[session], font=serif(96), fill=BEIGE, anchor="mm")
    d.line((cx - 150, 325, cx + 150, 325), fill=GOLD_L[:3] + (200,), width=2)

    y = top
    _spaced(d, (cx, y + 20), item["title"].upper(), f_title, GOLD_L, 8)
    y += 90
    for ln in lines:
        d.text((cx + 2, y + lh // 2 + 3), ln, font=f, fill=(0, 0, 0, 160), anchor="mm")
        d.text((cx, y + lh // 2), ln, font=f, fill=(255, 255, 255, 255), anchor="mm")
        y += lh
    y += 40
    if item.get("count"):
        cw = f_count.getlength(item["count"]) + 80
        d.rounded_rectangle((cx - cw / 2, y, cx + cw / 2, y + 64), radius=32, fill=GOLD_L[:3] + (235,))
        d.text((cx, y + 32), item["count"], font=f_count, fill=(30, 40, 35, 255), anchor="mm")
        y += 90
    d.text((cx, y + 24), item["source"], font=f_ref, fill=GOLD_L, anchor="mm")
    d.text((cx, y + 72), item["credit"], font=f_small, fill=(236, 230, 214, 170), anchor="mm")

    d.text((cx, H - 200), f"{idx} / {total}", font=sans(34, 400), fill=(255, 255, 255, 200), anchor="mm")
    _spaced(d, (cx, H - 130), "DAILY SERENITY", sans(30, 500), (243, 235, 221, 200), 12)
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["morning", "evening"])
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    session = args.session or ("morning" if dt.datetime.now(dt.timezone.utc).hour < 12 else "evening")
    cfg = load_json(ROOT / "config.json")
    en = cfg.get("en", {})
    history = load_json(HISTORY) if HISTORY.exists() else {"sessions": []}

    items = pick(session, history, en.get("adhkar", {}).get("per_session", 3))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    bg, bg_id = background_photo({h.get("background") for h in history["sessions"][-20:]})
    print(f"🕊️  {HEAD[session]} | background: {bg_id}")
    frames = []
    for k, it in enumerate(items, 1):
        frames.append(render(it, session, k, len(items), bg, OUT / f"story_{k}.jpg"))
        print(f"   {k}. {it['id']} – {it['source']}")
    if not args.publish:
        return

    from ..publish_meta import publish_facebook_photo, story_facebook_photo, story_instagram_photo
    st = en.get("stories", {"facebook": True, "instagram": True})
    results = []
    for fr in frames:
        r, url = {}, None
        if st.get("facebook"):
            try:
                x = story_facebook_photo(cfg, fr)
                url = x.pop("image_url", None)
                r["facebook"] = {"ok": True, **x}
            except Exception as e:  # noqa: BLE001
                r["facebook"] = {"ok": False, "error": type(e).__name__}
        if st.get("instagram"):
            try:
                if not url:
                    url = publish_facebook_photo(cfg, fr, "", published=False)["image_url"]
                r["instagram"] = {"ok": True, **story_instagram_photo(cfg, url)}
            except Exception as e:  # noqa: BLE001
                r["instagram"] = {"ok": False, "error": type(e).__name__}
        print(f"   📲 {fr.name}: {r}")
        results.append(r)

    history["sessions"].append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                "session": session, "ids": [i["id"] for i in items], "background": bg_id,
                                "results": results})
    history["sessions"] = history["sessions"][-200:]
    save_json(HISTORY, history)
    oks = [v["ok"] for r in results for v in r.values()]
    if oks and not any(oks):
        sys.exit(1)


if __name__ == "__main__":
    main()

