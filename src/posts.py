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

TITLES = {"hadith": "حديث شريف", "dua": "دعاء", "quran_dua": "دعاء من القرآن الكريم"}
OPENERS = {
    "hadith": ["من هدي النبي ﷺ 🤍", "حديث شريف يستحق التأمل 🤍", "من كنوز السنة النبوية 🤍", "سنّة تحييها اليوم 🤍"],
    "dua": ["ردّد هذا الدعاء 🤲", "دعاء من السنة النبوية 🤲", "من أدعية النبي ﷺ 🤲", "لا تنسَ هذا الدعاء اليوم 🤲"],
    "quran_dua": ["دعاء من القرآن الكريم 🤲", "ادعُ بها من قلبك 🤲", "من أدعية الأنبياء في القرآن 🤲"],
}
CTAS = ["شاركها… لعلها تكون صدقة جارية لك 🤍", "انشرها فالدال على الخير كفاعله 🤍",
        "لا تمرّ دون أن تصلي على النبي ﷺ"]
DUA_CTAS = ["اكتب «آمين» 🤲", "شاركها لعل دعوة تصيب قلبًا محتاجًا 🤍", "ادعُ بها لنفسك ولمن تحب 🤲"]
HASHTAGS = {
    "hadith": ["#حديث_شريف", "#السنة_النبوية", "#سكينة_يومية", "#اسلاميات", "#حديث_صحيح"],
    "dua": ["#دعاء", "#أدعية", "#سكينة_يومية", "#أذكار", "#اسلاميات"],
    "quran_dua": ["#دعاء", "#أدعية_من_القرآن", "#سكينة_يومية", "#قرآن_كريم", "#اسلاميات"],
}
PHOTO_QUERIES = ["waterfall", "misty mountains", "mountain lake", "forest sunlight", "ocean sunset",
                 "calm sea", "green valley", "desert dunes", "flower field", "clouds sky", "autumn forest",
                 "river landscape"]


def _font(path, size):
    if not path.exists():
        download(FONT_URLS[path], path)
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)


# ------------------------------------------------------------------ content
def source_line(item):
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


def render_post(item, text, src, bg_path, dest, handle="سَكينة يومية"):
    if bg_path:
        bg = Image.open(bg_path).convert("RGB")
        s = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
        l, t = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((l, t, l + W, t + H))
        bg = ImageEnhance.Brightness(bg).enhance(0.62)
    else:
        bg = Image.new("RGB", (W, H), (22, 60, 50))
    img = bg.convert("RGBA")

    is_quran = item["type"] == "quran_dua"
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
    pre = "قال رسول الله ﷺ:" if item["type"] == "hadith" else ""

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
    d.text((cx, y + 30), TITLES[item["type"]], font=f_title, fill=GOLD + (255,), anchor="mm", direction="rtl")
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


def build_caption(item, text, src, n_tags=5):
    opener = random.choice(OPENERS[item["type"]])
    if item["type"] == "hadith":
        body = f"قال رسول الله ﷺ:\n«{text}»\n\n📚 {src}"
    elif item["type"] == "dua":
        body = f"«{text}»\n\n📚 {src}"
    else:
        body = f"﴿ {text} ﴾\n\n📖 {src}"
    tags = HASHTAGS[item["type"]][:]
    if item.get("bukhari"):
        tags.insert(2, "#صحيح_البخاري")
    elif item.get("muslim"):
        tags.insert(2, "#صحيح_مسلم")
    cta = random.choice(DUA_CTAS if item["type"] != "hadith" else CTAS)
    return "\n\n".join([opener, body, cta, " ".join(tags[:n_tags])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--id")
    args = ap.parse_args()
    cfg = load_json(ROOT / "config.json")
    history = load_json(HISTORY) if HISTORY.exists() else {"posts": []}

    items = load_json(DATA / "posts.json")["items"]
    item = next(i for i in items if i["id"] == args.id) if args.id else pick_item(history)
    if item["type"] == "quran_dua":
        text, src = quran_text(item)
    else:
        text, src = item["text"], source_line(item)
    print(f"📝 {item['id']} ({item['type']}): {src}")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    used = {p.get("background") for p in history["posts"][-60:]}
    bg, bg_id = background_photo(used)
    print(f"🌄 Background: {bg_id}")
    image = render_post(item, text, src, bg, OUT / "post.jpg")
    story_img = render_story(image, bg, OUT / "story.jpg")
    caps = {p: build_caption(item, text, src, cfg["posts"]["platforms"][p]["hashtags"])
            for p in cfg["posts"]["platforms"]}
    for p, c in caps.items():
        (OUT / f"caption_{p}.txt").write_text(c, encoding="utf-8")
    print("🖼️  Post ready:", image)

    if not args.publish:
        print("\n--- caption ---\n" + caps["instagram"])
        return

    from .publish_meta import publish_facebook_photo, publish_instagram_image
    results, fb_url = {}, None
    pc = cfg["posts"]["platforms"]
    if pc.get("facebook", {}).get("enabled"):
        try:
            r = publish_facebook_photo(cfg, image, caps["facebook"])
            fb_url = r.pop("image_url", None)
            results["facebook"] = {"ok": True, **r}
        except Exception as e:  # noqa: BLE001
            results["facebook"] = {"ok": False, "error": str(e)[:400]}
    if pc.get("instagram", {}).get("enabled"):
        try:
            results["instagram"] = {"ok": True, **publish_instagram_image(cfg, image, caps["instagram"], fb_url)}
        except Exception as e:  # noqa: BLE001
            results["instagram"] = {"ok": False, "error": str(e)[:400]}
    # ستوري للبوست على فيسبوك وإنستجرام
    st = cfg.get("stories", {})
    from .publish_meta import story_facebook_photo, story_instagram_photo
    story_url = None  # رابط صورة الستوري (1080×1920) – بيطلع من رفعها على فيسبوك
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
                from .publish_meta import publish_facebook_photo
                story_url = publish_facebook_photo(cfg, story_img, "", published=False)["image_url"]
            results["instagram_story"] = {"ok": True, **story_instagram_photo(cfg, story_url)}
        except Exception as e:  # noqa: BLE001
            results["instagram_story"] = {"ok": False, "error": str(e)[:300]}
    print(results)
    history["posts"].append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                             "id": item["id"], "type": item["type"], "background": bg_id, "results": results})
    save_json(HISTORY, history)
    main_ok = [r["ok"] for k, r in results.items() if not k.endswith("_story")]
    if main_ok and not any(main_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
