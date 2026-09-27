"""بوست يومي (صورة 1080×1440) فيه دعاء أو حديث صحيح على منظر طبيعي – بيتنشر على فيسبوك وإنستجرام بس.

المحتوى من data/posts.json:
  - hadith / dua : نص منقول حرفيًا من صحيح البخاري وصحيح مسلم مع رقم الحديث (اتراجع آليًا).
  - quran_dua    : أدعية من القرآن، نصها بيتجاب وقت النشر من Quran.com.
التشغيل:
  python -m src.posts             # يولّد البوست في out_post/ بدون نشر
  python -m src.posts --publish   # يولّد وينشر
"""
import argparse
import datetime as dt
import os
import random
import shutil
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .common import CACHE, DATA, ROOT, ar_num, download, http_get, load_json, save_json
from .render import FONT_URLS, QURAN_FONT, UI_BOLD, UI_FONT

OUT = ROOT / "out_post"
HISTORY = ROOT / "posts_history.json"
W, H = 1080, 1440
GOLD = (236, 214, 160)

TITLES = {"hadith": "حديث شريف", "dua": "دعاء", "quran_dua": "دعاء من القرآن الكريم", "quran": "من القرآن الكريم",
          "athar": "من هدي النبي ﷺ"}
OPENERS = {
    "hadith": ["من هدي النبي ﷺ 🤍", "حديث شريف يستحق التأمل 🤍", "من كنوز السنة النبوية 🤍", "سنّة تحييها اليوم 🤍"],
    "dua": ["ردّد هذا الدعاء 🤲", "دعاء من السنة النبوية 🤲", "من أدعية النبي ﷺ 🤲", "لا تنسَ هذا الدعاء اليوم 🤲"],
    "quran_dua": ["دعاء من القرآن الكريم 🤲", "ادعُ بها من قلبك 🤲", "من أدعية الأنبياء في القرآن 🤲"],
    "quran": ["آية تستحق التأمل 🤍", "من نور القرآن الكريم 🤍"],
    "athar": ["من هدي النبي ﷺ 🤍", "سنّة تحييها 🤍"],
}
CTAS = ["شاركها… لعلها تكون صدقة جارية لك 🤍", "انشرها فالدال على الخير كفاعله 🤍",
        "لا تمرّ دون أن تصلي على النبي ﷺ"]
DUA_CTAS = ["اكتب «آمين» 🤲", "شاركها لعل دعوة تصيب قلبًا محتاجًا 🤍", "ادعُ بها لنفسك ولمن تحب 🤲"]
HASHTAGS = {
    "hadith": ["#حديث_شريف", "#السنة_النبوية", "#سكينة_يومية", "#اسلاميات", "#حديث_صحيح"],
    "dua": ["#دعاء", "#أدعية", "#سكينة_يومية", "#أذكار", "#اسلاميات"],
    "quran_dua": ["#دعاء", "#أدعية_من_القرآن", "#سكينة_يومية", "#قرآن_كريم", "#اسلاميات"],
    "quran": ["#قرآن_كريم", "#تدبر", "#سكينة_يومية", "#اسلاميات", "#آيات"],
    "athar": ["#السنة_النبوية", "#هدي_النبي", "#سكينة_يومية", "#اسلاميات", "#حديث_صحيح"],
}
# كاروسيل الأيام العادية: مجموعة من نفس النوع
CAROUSEL_SETS = [
    {"type": "quran_dua", "title": "أدعية من القرآن الكريم", "sub": "ادعُ بها في يومك", "n": 4},
    {"type": "hadith", "title": "من كنوز السنة النبوية", "sub": "أحاديث صحيحة من البخاري ومسلم", "n": 4},
    {"type": "dua", "title": "أدعية نبوية", "sub": "من دعاء النبي ﷺ", "n": 4},
]
PHOTO_QUERIES = ["waterfall", "misty mountains", "mountain lake", "forest sunlight", "ocean sunset",
                 "calm sea", "green valley", "desert dunes", "flower field", "clouds sky", "autumn forest",
                 "river landscape"]


def _font(path, size):
    if not path.exists():
        download(FONT_URLS[path], path)
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)


# ------------------------------------------------------------------ content
def source_line(item):
    if item.get("source"):
        return item["source"]
    b, m = item.get("bukhari"), item.get("muslim")
    if b and m:
        return f"متفق عليه — البخاري ({ar_num(b)}) ومسلم ({ar_num(m)})"
    if b:
        return f"رواه البخاري ({ar_num(b)})"
    return f"رواه مسلم ({ar_num(m)})"


def quran_text(item):
    surahs = load_json(DATA / "surahs.json")
    parts = []
    for a in range(item["from"], item["to"] + 1):
        key = f"{item['surah']}:{a}"
        try:
            t = http_get(f"https://api.quran.com/api/v4/verses/by_key/{key}",
                         params={"fields": "text_uthmani"}).json()["verse"]["text_uthmani"]
        except Exception:  # noqa: BLE001
            t = http_get(f"https://api.alquran.cloud/v1/ayah/{key}/quran-uthmani").json()["data"]["text"]
        parts.append(f"{t.replace('۞', '').strip()} ۝{ar_num(a)}")
    name = surahs[item["surah"] - 1]["name"]
    rng = f"الآية {ar_num(item['from'])}" if item["from"] == item["to"] else \
        f"الآيات {ar_num(item['from'])}–{ar_num(item['to'])}"
    return " ".join(parts), f"سورة {name} — {rng}"


def pick_item(history):
    items = load_json(DATA / "posts.json")["items"]
    recent = {p["id"] for p in history["posts"][-35:]}
    last_type = history["posts"][-1]["type"] if history["posts"] else None
    fresh = [i for i in items if i["id"] not in recent] or items
    # نبدّل بين الحديث والدعاء كل يوم
    prefer = [i for i in fresh if (i["type"] == "hadith") != (last_type == "hadith")] or fresh
    return random.choice(prefer)


# ------------------------------------------------------------------ background photo
def background_photo(used):
    key = os.getenv("PEXELS_API_KEY")
    local = sorted((ROOT / "backgrounds_images").glob("*.jp*g")) + sorted((ROOT / "backgrounds_images").glob("*.png"))
    fresh_local = [p for p in local if f"local:{p.name}" not in used]
    if fresh_local:
        p = random.choice(fresh_local)
        return p, f"local:{p.name}"
    if key:
        qs = PHOTO_QUERIES[:]
        random.shuffle(qs)
        for q in qs[:4]:
            try:
                r = http_get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                             params={"query": q, "orientation": "portrait", "size": "large", "per_page": 40})
                photos = [p for p in r.json().get("photos", []) if f"pexels:{p['id']}" not in used]
                if photos:
                    p = random.choice(photos)
                    url = f"{p['src']['original']}?auto=compress&cs=tinysrgb&w=1440"
                    return download(url, CACHE / "photos" / f"pexels_{p['id']}.jpg"), f"pexels:{p['id']}"
            except Exception as e:  # noqa: BLE001
                print(f"  pexels photo failed: {e}")
    if local:
        p = random.choice(local)
        return p, f"local:{p.name}"
    return None, "generated"


# ------------------------------------------------------------------ rendering
def _wrap(text, font, max_w):
    lines, cur = [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if not cur or font.getlength(trial, direction="rtl") <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def _bg(bg_path, w, h, bright=0.62):
    if bg_path:
        bg = Image.open(bg_path).convert("RGB")
        s = max(w / bg.width, h / bg.height)
        bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
        l, t = (bg.width - w) // 2, (bg.height - h) // 2
        return ImageEnhance.Brightness(bg.crop((l, t, l + w, t + h))).enhance(bright)
    return Image.new("RGB", (w, h), (22, 60, 50))


def item_text(item):
    """(النص، المصدر) لأي عنصر: quran/quran_dua بيتجاب من Quran.com، الباقي من الملف."""
    if item["type"] in ("quran", "quran_dua"):
        return quran_text(item)
    return item["text"], source_line(item)


def render_post(item, text, src, bg_path, dest, handle="سَكينة يومية", title=None, page=None):
    img = _bg(bg_path, W, H).convert("RGBA")

    is_quran = item["type"] in ("quran_dua", "quran")
    body_font_path = QURAN_FONT if is_quran else UI_BOLD
    max_w, max_h = W - 200, 760
    size = 70
    while True:
        f_body = _font(body_font_path, size)
        lines = _wrap(text, f_body, max_w)
        lh = int(size * (1.95 if is_quran else 1.75))
        if len(lines) * lh <= max_h or size <= 34:
            break
        size -= 2

    f_title = _font(UI_BOLD, 50)
    f_pre = _font(UI_FONT, 42)
    f_src = _font(UI_FONT, 38)
    f_handle = _font(UI_BOLD, 36)
    pre = item.get("pre") or ("قال رسول الله ﷺ:" if item["type"] in ("hadith",) else "")
    title = title or item.get("title") or TITLES[item["type"]]

    block = 96 + (70 if pre else 0) + len(lines) * lh + 40 + 60
    top = (H - block) // 2 - 10
    cx = W // 2

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((60, top - 60, W - 60, top + block + 50), radius=44,
                                            fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, panel.filter(ImageFilter.GaussianBlur(16)))

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d_s = ImageDraw.Draw(shadow)
    d = ImageDraw.Draw(img)

    y = top
    d.text((cx, y + 30), title, font=f_title, fill=GOLD + (255,), anchor="mm", direction="rtl")
    y += 72
    d.line((cx - 120, y, cx + 120, y), fill=GOLD + (160,), width=2)
    y += 24
    if pre:
        d.text((cx, y + 30), pre, font=f_pre, fill=(255, 255, 255, 225), anchor="mm", direction="rtl")
        y += 70
    body_y = y
    for ln in lines:
        d_s.text((cx + 3, y + lh // 2 + 3), ln, font=f_body, fill=(0, 0, 0, 200), anchor="mm", direction="rtl")
        y += lh
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(img)
    y = body_y
    for ln in lines:
        d.text((cx, y + lh // 2), ln, font=f_body, fill=(255, 255, 255, 255), anchor="mm", direction="rtl")
        y += lh
    y += 30
    sw = d.textlength(src, font=f_src)  # centre manually (mixed Arabic + digits)
    d.text((cx + sw / 2, y + 25), src, font=f_src, fill=GOLD + (255,), anchor="rm")

    d.text((cx, H - 70), handle, font=f_handle, fill=(255, 255, 255, 170), anchor="mm", direction="rtl")
    if page:
        d.text((W - 90, 80), page, font=_font(UI_FONT, 34), fill=(255, 255, 255, 190), anchor="mm")
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def render_cover(title, sub, bg_path, dest, badge="", handle="سَكينة يومية", hint="اسحب للمزيد"):
    """أول سلايد في الكاروسيل / بوست المناسبة: عنوان كبير في النص."""
    img = _bg(bg_path, W, H, 0.55).convert("RGBA")
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((80, H // 2 - 300, W - 80, H // 2 + 300), radius=48, fill=(0, 0, 0, 140))
    img = Image.alpha_composite(img, panel.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)
    cx = W // 2
    size = 110
    while _font(UI_BOLD, size).getlength(title, direction="rtl") > W - 240 and size > 60:
        size -= 4
    if badge:
        d.text((cx, H // 2 - 210), badge, font=_font(UI_FONT, 40), fill=GOLD + (255,), anchor="mm", direction="rtl")
    d.text((cx, H // 2 - 50), title, font=_font(UI_BOLD, size), fill=(255, 255, 255, 255), anchor="mm",
           direction="rtl")
    d.line((cx - 150, H // 2 + 50, cx + 150, H // 2 + 50), fill=GOLD + (200,), width=3)
    if sub:
        f_sub = _font(UI_FONT, 46)
        for i, ln in enumerate(_wrap(sub, f_sub, W - 280)[:2]):
            d.text((cx, H // 2 + 125 + i * 70), ln, font=f_sub, fill=(255, 255, 255, 230), anchor="mm",
                   direction="rtl")
    if hint:
        d.text((cx, H - 150), hint, font=_font(UI_FONT, 36), fill=(255, 255, 255, 170), anchor="mm", direction="rtl")
    d.text((cx, H - 70), handle, font=_font(UI_BOLD, 36), fill=(255, 255, 255, 170), anchor="mm", direction="rtl")
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def render_story(post_path, bg_path, dest, label="منشور جديد على الصفحة"):
    """ستوري 1080×1920: نفس البوست في النص فوق نسخة مغبّشة من نفس الخلفية."""
    SW, SH = 1080, 1920
    post = Image.open(post_path).convert("RGB")
    base = Image.open(bg_path).convert("RGB") if bg_path else post.copy()
    s = max(SW / base.width, SH / base.height)
    base = base.resize((int(base.width * s) + 1, int(base.height * s) + 1), Image.LANCZOS)
    l, t = (base.width - SW) // 2, (base.height - SH) // 2
    base = base.crop((l, t, l + SW, t + SH)).filter(ImageFilter.GaussianBlur(28))
    base = ImageEnhance.Brightness(base).enhance(0.55).convert("RGBA")

    pw = 960
    ph = int(post.height * pw / post.width)
    card = post.resize((pw, ph), Image.LANCZOS)
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), radius=36, fill=255)
    x, y = (SW - pw) // 2, (SH - ph) // 2 + 20
    shadow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x + 6, y + 14, x + pw + 6, y + ph + 14), radius=36,
                                             fill=(0, 0, 0, 150))
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(18)))
    base.paste(card, (x, y), mask)
    d = ImageDraw.Draw(base)
    d.text((SW // 2, y - 70), label, font=_font(UI_BOLD, 46), fill=(255, 255, 255, 235), anchor="mm",
           direction="rtl")
    base.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def _body(item, text, src):
    if item["type"] == "hadith":
        return f"{item.get('pre') or 'قال رسول الله ﷺ:'}\n«{text}»\n\n📚 {src}"
    if item["type"] == "athar":
        return f"{item['pre']}\n«{text}»\n\n📚 {src}"
    if item["type"] == "dua":
        return f"«{text}»\n\n📚 {src}"
    return f"﴿ {text} ﴾\n\n📖 {src}"


def _tags(types, items, extra, n):
    tags = list(extra or [])
    for t in types:
        tags += HASHTAGS[t]
    if any(i.get("bukhari") for i in items):
        tags.insert(min(2, len(tags)), "#صحيح_البخاري")
    elif any(i.get("muslim") for i in items):
        tags.insert(min(2, len(tags)), "#صحيح_مسلم")
    if "#سكينة_يومية" not in tags[:n]:
        tags.insert(n - 1, "#سكينة_يومية")
    return " ".join(list(dict.fromkeys(tags))[:n])


def build_caption(item, text, src, n_tags=5, occ=None):
    opener = occ["opener"] if occ else random.choice(OPENERS[item["type"]])
    cta = random.choice(CTAS if item["type"] in ("hadith", "athar") else DUA_CTAS)
    tags = _tags([item["type"]], [item], occ.get("hashtags") if occ else None, n_tags)
    return "\n\n".join([opener, _body(item, text, src), cta, tags])


def build_carousel_caption(slides, n_tags=5, occ=None, title=""):
    opener = occ["opener"] if occ else f"{title} 🤍 اسحب للنهاية"
    parts = [opener]
    for it, text, src in slides:
        parts.append(_body(it, text, src))
    parts.append(random.choice(["احفظها وشاركها… لعلها تكون صدقة جارية لك 🤍", "شاركها مع من تحب 🤍",
                                "اكتب «آمين» وشاركها 🤲"]))
    parts.append(_tags(list(dict.fromkeys(i["type"] for i, _, _ in slides)), [i for i, _, _ in slides],
                       occ.get("hashtags") if occ else None, n_tags))
    cap = "\n\n".join(parts)
    while len(cap) > 2150 and len(parts) > 4:  # حد إنستجرام ٢٢٠٠ حرف
        parts.pop(-3)
        cap = "\n\n".join(parts)
    return cap


# ------------------------------------------------------------------ what to publish today
def recent_ids(history, n=40):
    out = set()
    for p in history["posts"][-n:]:
        out.update(p.get("ids") or [p.get("id")])
    return out


def plan_today(cfg, history, force_kind=None, date=None):
    """يقرر منشور الصبح: مناسبة/جمعة، وإلا بالتناوب صورة ↔ كاروسيل."""
    from . import occasions
    ctx = occasions.today(cfg, date)
    occ = ctx["occasion"]
    items = load_json(DATA / "posts.json")["items"]
    recent = recent_ids(history)
    print(f"📅 {ctx['date']} | {ctx['hijri_text']} | occasion: {occ['id'] if occ else '-'}")

    if occ and not force_kind:
        lib = [occasions.item(k) for k in occ["items"]]
        if occ["morning"] == "carousel":
            return {"kind": "carousel", "occ": occ, "items": lib, "title": occ.get("cover", occ["name"]),
                    "sub": occ.get("cover_sub", ""), "ctx": ctx}
        fresh = [i for i in lib if i["id"] not in recent] or lib
        # نلف على القائمة بالترتيب عشان كل يوم في رمضان مثلًا يطلع حديث مختلف
        return {"kind": "post", "occ": occ, "items": [fresh[0]], "title": occ["name"], "ctx": ctx}

    normal = [p for p in history["posts"] if not p.get("occasion")]
    last_kind = normal[-1].get("kind", "post") if normal else "carousel"
    kind = force_kind or ("carousel" if last_kind == "post" else "post")
    if kind == "carousel":
        last_sets = [p.get("set") for p in history["posts"] if p.get("kind") == "carousel"]
        sets = sorted(CAROUSEL_SETS, key=lambda cs: (cs["type"] in last_sets[-2:], random.random()))
        cs = sets[0]
        pool = [i for i in items if i["type"] == cs["type"] and i["id"] not in recent] or \
               [i for i in items if i["type"] == cs["type"]]
        chosen = random.sample(pool, min(cs["n"], len(pool)))
        return {"kind": "carousel", "occ": None, "items": chosen, "title": cs["title"], "sub": cs["sub"],
                "set": cs["type"], "ctx": ctx}
    return {"kind": "post", "occ": None, "items": [pick_item(history)], "title": None, "ctx": ctx}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--kind", choices=["post", "carousel"])
    ap.add_argument("--date", help="YYYY-MM-DD لتجربة مناسبة معينة")
    args = ap.parse_args()
    cfg = load_json(ROOT / "config.json")
    history = load_json(HISTORY) if HISTORY.exists() else {"posts": []}
    date = dt.date.fromisoformat(args.date) if args.date else None

    if args.id:
        items = load_json(DATA / "posts.json")["items"]
        plan = {"kind": "post", "occ": None, "items": [next(i for i in items if i["id"] == args.id)], "title": None}
    else:
        plan = plan_today(cfg, history, args.kind, date)
    occ = plan["occ"]

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    used = {p.get("background") for p in history["posts"][-60:]}
    bg, bg_id = background_photo(used)
    print(f"🌄 Background: {bg_id}")

    slides = []
    for it in plan["items"]:
        text, src = item_text(it)
        slides.append((it, text, src))
        print(f"📝 {it['id']} ({it['type']}): {src}")
    pc = cfg["posts"]["platforms"]

    if plan["kind"] == "carousel":
        n = len(slides) + 1
        images = [render_cover(plan["title"], plan.get("sub", ""), bg, OUT / "slide_00.jpg",
                               badge=(plan["ctx"]["hijri_text"] if occ else ""), hint="اسحب للمزيد")]
        for k, (it, text, src) in enumerate(slides, 1):
            images.append(render_post(it, text, src, bg, OUT / f"slide_{k:02d}.jpg", page=f"{k + 1}/{n}"))
        image = images[0]
        caps = {p: build_carousel_caption(slides, pc[p]["hashtags"], occ, plan["title"]) for p in pc}
    else:
        it, text, src = slides[0]
        image = render_post(it, text, src, bg, OUT / "post.jpg", title=plan.get("title"))
        images = [image]
        caps = {p: build_caption(it, text, src, pc[p]["hashtags"], occ) for p in pc}
    if images[0] != OUT / "post.jpg":
        shutil.copy(images[0], OUT / "post.jpg")
    story_img = render_story(images[0], bg, OUT / "story.jpg")
    for p, c in caps.items():
        (OUT / f"caption_{p}.txt").write_text(c, encoding="utf-8")
    print(f"🖼️  {plan['kind']} ready: {len(images)} image(s)")

    if not args.publish:
        print("\n--- caption ---\n" + caps["instagram"])
        return

    from .publish_meta import (publish_facebook_carousel, publish_facebook_photo, publish_instagram_carousel,
                               publish_instagram_image, story_facebook_photo, story_instagram_photo)
    results, fb_urls = {}, None
    if pc.get("facebook", {}).get("enabled"):
        try:
            if plan["kind"] == "carousel":
                r = publish_facebook_carousel(cfg, images, caps["facebook"])
                fb_urls = r.pop("image_urls", None)
            else:
                r = publish_facebook_photo(cfg, image, caps["facebook"])
                fb_urls = [r.pop("image_url", None)]
            results["facebook"] = {"ok": True, **r}
        except Exception as e:  # noqa: BLE001
            results["facebook"] = {"ok": False, "error": str(e)[:400]}
    if pc.get("instagram", {}).get("enabled"):
        try:
            if plan["kind"] == "carousel":
                results["instagram"] = {"ok": True, **publish_instagram_carousel(cfg, images, caps["instagram"], fb_urls)}
            else:
                results["instagram"] = {"ok": True, **publish_instagram_image(cfg, image, caps["instagram"],
                                                                             (fb_urls or [None])[0])}
        except Exception as e:  # noqa: BLE001
            results["instagram"] = {"ok": False, "error": str(e)[:400]}
    # ستوري للمنشور على فيسبوك وإنستجرام (١٠٨٠×١٩٢٠)
    st = cfg.get("stories", {})
    story_url = None
    if st.get("facebook") and pc.get("facebook", {}).get("enabled"):
        try:
            r = story_facebook_photo(cfg, story_img)
            story_url = r.pop("image_url", None)
            results["facebook_story"] = {"ok": True, **r}
        except Exception as e:  # noqa: BLE001
            results["facebook_story"] = {"ok": False, "error": str(e)[:300]}
    if st.get("instagram") and pc.get("instagram", {}).get("enabled"):
        try:
            if not story_url:
                story_url = publish_facebook_photo(cfg, story_img, "", published=False)["image_url"]
            results["instagram_story"] = {"ok": True, **story_instagram_photo(cfg, story_url)}
        except Exception as e:  # noqa: BLE001
            results["instagram_story"] = {"ok": False, "error": str(e)[:300]}
    print(results)
    ids = [it["id"] for it, _, _ in slides]
    history["posts"].append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                             "kind": plan["kind"], "id": ids[0], "ids": ids, "type": slides[0][0]["type"],
                             "set": plan.get("set"), "occasion": occ["id"] if occ else None,
                             "background": bg_id, "results": results})
    save_json(HISTORY, history)
    main_ok = [r["ok"] for k, r in results.items() if not k.endswith("_story")]
    if main_ok and not any(main_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
