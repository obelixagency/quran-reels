"""Daily Serenity – daily feed post on Facebook + Instagram (English), one a day.

Alternates day by day: a single image post  <->  a carousel (cover + 4 slides).
  single  : a hadith, a dua or a short Quran passage (Pickthall), rotating the three
  carousel: "Duas from the Sunnah" / "Words of the Prophet ﷺ" / "Verses to calm your heart"
Content: data/en/hadith.json + dua.json (Sahih al-Bukhari / Sahih Muslim) and Pickthall (public domain).
Also posts a story that points to the new post.
  python -m src.en.posts                       # render only (out_en_post/)
  python -m src.en.posts --kind carousel       # force a kind
  python -m src.en.posts --publish
"""
import argparse
import datetime as dt
import random
import shutil
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from ..common import DATA, ROOT, load_json, save_json
from ..posts import _bg, background_photo
from . import captions
from .video import BEIGE, GOLD_L, _spaced, _wrap, for_video, sans, serif

OUT = ROOT / "out_en_post"
HISTORY = ROOT / "posts_history_en.json"
W, H = 1080, 1350  # 4:5 – the tallest feed format on Instagram
KINDS = ("hadith", "dua", "quran")
LABEL = {"hadith": "Hadith", "dua": "Dua from the Sunnah", "quran": "From the Quran"}
SETS = [
    {"type": "dua", "title": "Duas from the Sunnah", "sub": "Save these for the days you need them", "n": 4},
    {"type": "hadith", "title": "Words of the Prophet", "sub": "Timeless lessons from Bukhari & Muslim", "n": 4},
    {"type": "quran", "title": "Verses to Calm Your Heart", "sub": "From the Quran, in English", "n": 4},
]
MAX_QURAN_WORDS = 75


# ------------------------------------------------------------------ content
def _quran_items():
    passages = load_json(DATA / "en" / "passages.json")["items"]
    verses = load_json(DATA / "en" / "pickthall.json")["verses"]
    chapters = load_json(DATA / "en" / "chapters.json")
    out = []
    for p in passages:
        s, parts, last = p["surah"], [], None
        for a in range(p["from"], p["to"] + 1):
            t = verses.get(f"{s}:{a}")
            if not t:
                break
            if parts and len(" ".join(parts + [t]).split()) > MAX_QURAN_WORDS:
                break
            parts.append(t)
            last = a
        if not parts or len(" ".join(parts).split()) > MAX_QURAN_WORDS:
            continue
        ch = chapters[str(s)]
        ref = f"{p['from']}" if last == p["from"] else f"{p['from']}-{last}"
        out.append({"id": p["id"], "type": "quran", "en": " ".join(parts),
                    "v": {"verse_text": " ".join(parts), "surah_number": s, "ayah_ref": ref,
                          "surah_name": ch["name"], "surah_meaning": ch["meaning"]}})
    return out


def all_items():
    items = []
    for it in load_json(DATA / "en" / "hadith.json")["items"]:
        items.append({"id": it["id"], "type": "hadith", "en": it["en"], "intro": it.get("intro"),
                      "v": {"hadith_text": it["en"], "narrator": it["narrator"], "collection": it["collection"],
                            "hadith_number": it["number"], "intro": it.get("intro")}})
    for it in load_json(DATA / "en" / "dua.json")["items"]:
        items.append({"id": it["id"], "type": "dua", "en": it["en"], "intro": it.get("intro"),
                      "occasion": it.get("occasion", ""),
                      "v": {"dua_text": it["en"], "dua_occasion": it.get("occasion", ""),
                            "collection": it["collection"], "hadith_number": it["number"],
                            "intro": it.get("intro")}})
    return items + _quran_items()


def _recent(history, days):
    now = dt.datetime.now(dt.timezone.utc)
    out = set()
    for p in history:
        try:
            if now - dt.datetime.fromisoformat(p["date"]) < dt.timedelta(days=days):
                out.update(p.get("ids") or [p.get("id")])
        except Exception:  # noqa: BLE001
            pass
    return out


def plan_today(history, reels_history, force_kind=None):
    items = all_items()
    used = _recent(history["posts"], 60) | _recent(reels_history, 10)  # not what the reels just used
    last = history["posts"][-1] if history["posts"] else None
    kind = force_kind or ("carousel" if (last or {}).get("kind") == "post" else "post")
    if kind == "carousel":
        last_sets = [p.get("set") for p in history["posts"] if p.get("kind") == "carousel"]
        cs = sorted(SETS, key=lambda s: (s["type"] in last_sets[-2:], random.random()))[0]
        pool = [i for i in items if i["type"] == cs["type"] and i["id"] not in used] or \
               [i for i in items if i["type"] == cs["type"]]
        return {"kind": "carousel", "set": cs["type"], "title": cs["title"], "sub": cs["sub"],
                "items": random.sample(pool, min(cs["n"], len(pool)))}
    singles = [p.get("type") for p in history["posts"] if p.get("kind") == "post"]
    order = sorted(KINDS, key=lambda k: (k in singles[-2:], random.random()))
    for t in order:
        pool = [i for i in items if i["type"] == t and i["id"] not in used]
        if pool:
            return {"kind": "post", "set": None, "items": [random.choice(pool)]}
    return {"kind": "post", "set": None, "items": [random.choice(items)]}


def source_line(it):
    v = it["v"]
    if it["type"] == "quran":
        return f"Quran {v['surah_number']}:{v['ayah_ref']}  ·  Surah {v['surah_name']}"
    if it["type"] == "hadith":
        return f"{v['collection']} {v['hadith_number']}  ·  Narrated by {v['narrator']}"
    return f"{v['collection']} {v['hadith_number']}"


def intro_line(it):
    if it["type"] == "hadith":
        return for_video(it.get("intro") or "The Prophet ﷺ said:")
    if it["type"] == "dua":
        occ = it.get("occasion") or ""
        return for_video(it.get("intro") or (f"A dua {occ}:" if occ else "The Prophet ﷺ used to say:"))
    return ""


# ------------------------------------------------------------------ rendering
def _panel(img, box, alpha=150):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=44, fill=(20, 28, 24, alpha))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(16)))


def _fit_text(text, max_w, max_h, start=66, minimum=34, ratio=1.32):
    words = text.split()
    size = start
    while True:
        f = serif(size)
        lines = [" ".join(l) for l in _wrap(words, f, max_w)]
        lh = int(size * ratio)
        if len(lines) * lh <= max_h or size <= minimum:
            return f, lines, lh
        size -= 2


def render_slide(it, bg, dest, page=None):
    img = _bg(bg, W, H, 0.6).convert("RGBA")
    text = for_video(it["en"])
    if it["type"] != "quran":
        text = f"“{text}”"
    f, lines, lh = _fit_text(text, W - 230, 640)
    intro = intro_line(it)
    f_intro = serif(max(34, int(f.size * 0.72)))
    intro_lines = [" ".join(l) for l in _wrap(intro.split(), f_intro, W - 260)] if intro else []
    ilh = int(f_intro.size * 1.3)
    src = source_line(it)
    f_src = sans(28, 430)
    block = 70 + len(intro_lines) * ilh + (24 if intro_lines else 0) + len(lines) * lh + 36 + 44
    top = (H - block) // 2
    img = _panel(img, (66, top - 64, W - 66, top + block + 56))
    d = ImageDraw.Draw(img)
    cx = W // 2
    _spaced(d, (cx, top + 12), LABEL[it["type"]].upper(), sans(30, 500), GOLD_L, 8)
    d.line((cx - 90, top + 50, cx + 90, top + 50), fill=GOLD_L[:3] + (150,), width=2)
    y = top + 70
    for ln in intro_lines:
        d.text((cx, y + ilh // 2), ln, font=f_intro, fill=(243, 235, 221, 215), anchor="mm")
        y += ilh
    if intro_lines:
        y += 24
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    for k, ln in enumerate(lines):
        ds.text((cx + 2, y + k * lh + lh // 2 + 3), ln, font=f, fill=(0, 0, 0, 190), anchor="mm")
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(4)))
    d = ImageDraw.Draw(img)
    for k, ln in enumerate(lines):
        d.text((cx, y + k * lh + lh // 2), ln, font=f, fill=(255, 255, 255, 255), anchor="mm")
    y += len(lines) * lh + 36
    d.text((cx, y + 20), src, font=f_src, fill=GOLD_L, anchor="mm")
    if page:
        d.text((W - 96, 76), page, font=sans(30, 420), fill=(255, 255, 255, 190), anchor="mm")
    _spaced(d, (cx, H - 70), "DAILY SERENITY", sans(28, 500), (243, 235, 221, 190), 12)
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def render_cover(title, sub, bg, dest):
    img = _bg(bg, W, H, 0.5).convert("RGBA")
    img = _panel(img, (90, H // 2 - 270, W - 90, H // 2 + 270), 140)
    d = ImageDraw.Draw(img)
    cx = W // 2
    size = 112
    f = serif(size)
    lines = [" ".join(l) for l in _wrap(title.split(), f, W - 260)]
    while len(lines) > 2 and size > 70:
        size -= 6
        f = serif(size)
        lines = [" ".join(l) for l in _wrap(title.split(), f, W - 260)]
    lh = int(size * 1.08)
    y0 = H // 2 - 40 - (len(lines) - 1) * lh // 2
    _spaced(d, (cx, y0 - lh // 2 - 70), "DAILY SERENITY", sans(28, 500), GOLD_L, 12)
    for k, ln in enumerate(lines):
        d.text((cx, y0 + k * lh), ln, font=f, fill=BEIGE, anchor="mm")
    yl = y0 + (len(lines) - 1) * lh + lh // 2 + 34
    d.line((cx - 130, yl, cx + 130, yl), fill=GOLD_L[:3] + (200,), width=2)
    f_sub = sans(36, 400)
    for k, ln in enumerate([" ".join(l) for l in _wrap(sub.split(), f_sub, W - 300)][:2]):
        d.text((cx, yl + 60 + k * 52), ln, font=f_sub, fill=(255, 255, 255, 225), anchor="mm")
    _spaced(d, (cx, H - 130), "SWIPE FOR MORE", sans(30, 500), (255, 255, 255, 200), 8)
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def render_story(post_path, bg, dest):
    SW, SH = 1080, 1920
    post = Image.open(post_path).convert("RGB")
    base = Image.open(bg).convert("RGB") if bg else post.copy()
    s = max(SW / base.width, SH / base.height)
    base = base.resize((int(base.width * s) + 1, int(base.height * s) + 1), Image.LANCZOS)
    l, t = (base.width - SW) // 2, (base.height - SH) // 2
    base = base.crop((l, t, l + SW, t + SH)).filter(ImageFilter.GaussianBlur(28))
    base = ImageEnhance.Brightness(base).enhance(0.55).convert("RGBA")
    pw = 940
    ph = int(post.height * pw / post.width)
    card = post.resize((pw, ph), Image.LANCZOS)
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), radius=36, fill=255)
    x, y = (SW - pw) // 2, (SH - ph) // 2 + 30
    sh = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x + 6, y + 14, x + pw + 6, y + ph + 14), radius=36, fill=(0, 0, 0, 150))
    base = Image.alpha_composite(base, sh.filter(ImageFilter.GaussianBlur(18)))
    base.paste(card, (x, y), mask)
    d = ImageDraw.Draw(base)
    d.text((SW // 2, y - 80), "New on the page", font=serif(64), fill=BEIGE, anchor="mm")
    base.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


# ------------------------------------------------------------------ captions
def caption_single(it, history):
    kind = it["type"]
    hook, cta = captions.pick_hook_cta(kind, history["posts"])
    b = captions.body(kind, it["v"])
    credit = captions.CREDIT[kind]
    tags = " ".join(captions.HASHTAGS[kind][:6])
    return f"{hook} 🤍\n\n{b}\n\n{cta}\n\n{credit}\n\n{tags}", hook, cta


def caption_carousel(plan):
    t = plan["set"]
    parts = [f"{plan['title']} 🤍 Swipe to the end"]
    for it in plan["items"]:
        parts.append(captions.body(t, it["v"]))
    parts.append(random.choice(["Save this post and share it with someone you love 🤍",
                                "Which one touched your heart? Tell us below 👇",
                                "Save it for the day you need it 🤍"]))
    parts.append(captions.CREDIT[t])
    parts.append(" ".join(captions.HASHTAGS[t][:6]))
    cap = "\n\n".join(parts)
    while len(cap) > 2150 and len(parts) > 5:  # Instagram limit is 2,200 characters
        parts.pop(-4)
        cap = "\n\n".join(parts)
    return cap


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--kind", choices=["post", "carousel"])
    args = ap.parse_args()
    cfg = load_json(ROOT / "config.json")
    en = cfg.get("en", {})
    history = load_json(HISTORY) if HISTORY.exists() else {"posts": []}
    rh = ROOT / "history_en.json"
    reels_history = load_json(rh)["posts"] if rh.exists() else []

    plan = plan_today(history, reels_history, args.kind)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    bg, bg_id = background_photo({p.get("background") for p in history["posts"][-40:]})
    print(f"🌿 {plan['kind']} ({plan['set'] or plan['items'][0]['type']}) | background: {bg_id}")

    hook = cta = None
    if plan["kind"] == "carousel":
        n = len(plan["items"]) + 1
        images = [render_cover(plan["title"], plan["sub"], bg, OUT / "slide_00.jpg")]
        for k, it in enumerate(plan["items"], 1):
            images.append(render_slide(it, bg, OUT / f"slide_{k:02d}.jpg", page=f"{k + 1}/{n}"))
        cap = caption_carousel(plan)
    else:
        it = plan["items"][0]
        images = [render_slide(it, bg, OUT / "post.jpg")]
        cap, hook, cta = caption_single(it, history)
    for it in plan["items"]:
        print(f"   · {it['id']} – {source_line(it)}")
    story = render_story(images[0], bg, OUT / "story.jpg")
    (OUT / "caption.txt").write_text(cap, encoding="utf-8")
    print("\n" + cap)
    if not args.publish:
        return

    from ..publish_meta import (publish_facebook_carousel, publish_facebook_photo, publish_instagram_carousel,
                                publish_instagram_image, story_facebook_photo, story_instagram_photo)
    pc = en.get("platforms", {})
    results, urls = {}, None
    if pc.get("facebook", {}).get("enabled", True):
        try:
            if plan["kind"] == "carousel":
                r = publish_facebook_carousel(cfg, images, cap)
                urls = r.pop("image_urls", None)
            else:
                r = publish_facebook_photo(cfg, images[0], cap)
                urls = [r.pop("image_url", None)]
            results["facebook"] = {"ok": True, **r}
        except Exception as e:  # noqa: BLE001
            results["facebook"] = {"ok": False, "error": str(e)[:400]}
    if pc.get("instagram", {}).get("enabled", True):
        try:
            if plan["kind"] == "carousel":
                results["instagram"] = {"ok": True, **publish_instagram_carousel(cfg, images, cap, urls)}
            else:
                results["instagram"] = {"ok": True, **publish_instagram_image(cfg, images[0], cap, (urls or [None])[0])}
        except Exception as e:  # noqa: BLE001
            results["instagram"] = {"ok": False, "error": str(e)[:400]}
    st = en.get("stories", {"facebook": True, "instagram": True})
    story_url = None
    if st.get("facebook"):
        try:
            r = story_facebook_photo(cfg, story)
            story_url = r.pop("image_url", None)
            results["facebook_story"] = {"ok": True, **r}
        except Exception as e:  # noqa: BLE001
            results["facebook_story"] = {"ok": False, "error": str(e)[:300]}
    if st.get("instagram"):
        try:
            if not story_url:
                story_url = publish_facebook_photo(cfg, story, "", published=False)["image_url"]
            results["instagram_story"] = {"ok": True, **story_instagram_photo(cfg, story_url)}
        except Exception as e:  # noqa: BLE001
            results["instagram_story"] = {"ok": False, "error": str(e)[:300]}
    print(results)
    ids = [it["id"] for it in plan["items"]]
    history["posts"].append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                             "kind": plan["kind"], "id": ids[0], "ids": ids, "type": plan["items"][0]["type"],
                             "set": plan["set"], "hook": hook, "cta": cta, "background": bg_id,
                             "results": results})
    history["posts"] = history["posts"][-400:]
    save_json(HISTORY, history)
    main_ok = [r["ok"] for k, r in results.items() if not k.endswith("_story")]
    if main_ok and not any(main_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
