"""أذكار الصباح والمساء – ستوري ١٠٨٠×١٩٢٠ على فيسبوك وإنستجرام (٣ ستوريهات ورا بعض كل مرة).

الأذكار من data/adhkar.json (نصوص متراجعة على مصادرها). بنلف عليهم بحيث كل الأذكار تظهر خلال كام يوم.
  python -m src.adhkar                    # الجلسة تتحدد لوحدها حسب ساعة القاهرة (قبل ١٢ = صباح)
  python -m src.adhkar --session evening --publish
"""
import argparse
import datetime as dt
import shutil
import sys

from PIL import Image, ImageDraw, ImageFilter

from .common import DATA, ROOT, load_json, save_json
from .occasions import cairo_now
from .posts import GOLD, _bg, _font, _wrap, background_photo, quran_text
from .render import QURAN_FONT, UI_BOLD, UI_FONT

OUT = ROOT / "out_adhkar"
HISTORY = ROOT / "adhkar_history.json"
SW, SH = 1080, 1920
HEAD = {"morning": ("أذكار الصباح", "morning sunrise"), "evening": ("أذكار المساء", "evening sunset")}


def pick(session, history, n=3):
    items = [i for i in load_json(DATA / "adhkar.json")["items"] if i["session"] in (session, "both")]
    last = {}
    for k, h in enumerate(history["sessions"]):
        for i in h["ids"]:
            last[i] = k
    # الأقدم ظهورًا الأول، ونفضّل التنوع (ذكر + قرآن)
    items.sort(key=lambda i: last.get(i["id"], -1))
    chosen = items[:n]
    order = {"quran": 0, "dhikr": 1}
    return sorted(chosen, key=lambda i: order[i["kind"]])


def render(item, text, session, idx, total, bg_path, dest):
    head, _ = HEAD[session]
    img = _bg(bg_path, SW, SH, 0.5).filter(ImageFilter.GaussianBlur(3)).convert("RGBA")
    is_quran = item["kind"] == "quran"
    body_path = QURAN_FONT if is_quran else UI_BOLD
    max_w, max_h = SW - 200, 900
    size = 74
    while True:
        f_body = _font(body_path, size)
        lines = _wrap(text, f_body, max_w)
        lh = int(size * (1.9 if is_quran else 1.7))
        if len(lines) * lh <= max_h or size <= 34:
            break
        size -= 2

    note_lines = []
    f_note = _font(UI_FONT, 32)
    if item.get("note"):
        note_lines = _wrap(item["note"], f_note, max_w - 20)[:3]
    block = 100 + len(lines) * lh + 30 + (90 if item.get("count") else 0) + 70 + len(note_lines) * 48
    top = max(430, (SH - block) // 2 + 60)

    panel = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((60, top - 50, SW - 60, top + block + 40), radius=48,
                                            fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, panel.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    cx = SW // 2
    # العنوان فوق
    d.text((cx, 250), head, font=_font(UI_BOLD, 96), fill=GOLD + (255,), anchor="mm", direction="rtl")
    d.line((cx - 170, 330, cx + 170, 330), fill=GOLD + (200,), width=3)
    # عنوان الذكر
    y = top
    d.text((cx, y + 30), item["title"], font=_font(UI_BOLD, 50), fill=GOLD + (255,), anchor="mm", direction="rtl")
    y += 100
    for ln in lines:
        d.text((cx + 3, y + lh // 2 + 3), ln, font=f_body, fill=(0, 0, 0, 170), anchor="mm", direction="rtl")
        d.text((cx, y + lh // 2), ln, font=f_body, fill=(255, 255, 255, 255), anchor="mm", direction="rtl")
        y += lh
    y += 30
    if item.get("count"):
        f_c = _font(UI_BOLD, 40)
        cw = f_c.getlength(item["count"], direction="rtl") + 80
        d.rounded_rectangle((cx - cw / 2, y, cx + cw / 2, y + 66), radius=33, fill=GOLD + (235,))
        d.text((cx, y + 33), item["count"], font=f_c, fill=(30, 40, 35, 255), anchor="mm", direction="rtl")
        y += 90
    src = item["source_line"]
    f_src = _font(UI_FONT, 36)
    sw = d.textlength(src, font=f_src)
    d.text((cx + sw / 2, y + 30), src, font=f_src, fill=GOLD + (255,), anchor="rm")
    y += 70
    for ln in note_lines:
        d.text((cx, y + 20), ln, font=f_note, fill=(255, 255, 255, 200), anchor="mm", direction="rtl")
        y += 48
    # الترقيم والاسم تحت
    d.text((cx, SH - 190), f"{idx} / {total}", font=_font(UI_FONT, 38), fill=(255, 255, 255, 200), anchor="mm")
    d.text((cx, SH - 120), "سَكينة يومية", font=_font(UI_BOLD, 40), fill=(255, 255, 255, 190), anchor="mm",
           direction="rtl")
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["morning", "evening"])
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    session = args.session or ("morning" if cairo_now().hour < 12 else "evening")
    cfg = load_json(ROOT / "config.json")
    history = load_json(HISTORY) if HISTORY.exists() else {"sessions": []}
    n = cfg.get("adhkar", {}).get("per_session", 3)

    items = pick(session, history, n)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    used = {h.get("background") for h in history["sessions"][-20:]}
    bg, bg_id = background_photo(used)
    print(f"🕊️  {HEAD[session][0]} | background: {bg_id}")

    frames = []
    for k, it in enumerate(items, 1):
        if it["kind"] == "quran":
            text, src = quran_text(it)
            it = {**it, "source_line": src}
        else:
            text = it["text"]
            it = {**it, "source_line": it["source"]}
        frames.append(render(it, text, session, k, len(items), bg, OUT / f"story_{k}.jpg"))
        print(f"   {k}. {it['id']} – {it['source_line']}")

    if not args.publish:
        return

    from .publish_meta import story_facebook_photo, story_instagram_photo
    st = cfg.get("stories", {})
    results = []
    for f in frames:
        r, url = {}, None
        if st.get("facebook"):
            try:
                x = story_facebook_photo(cfg, f)
                url = x.pop("image_url", None)
                r["facebook"] = {"ok": True, **x}
            except Exception as e:  # noqa: BLE001
                r["facebook"] = {"ok": False, "error": str(e)[:300]}
        if st.get("instagram"):
            try:
                if not url:
                    from .publish_meta import publish_facebook_photo
                    url = publish_facebook_photo(cfg, f, "", published=False)["image_url"]
                r["instagram"] = {"ok": True, **story_instagram_photo(cfg, url)}
            except Exception as e:  # noqa: BLE001
                r["instagram"] = {"ok": False, "error": str(e)[:300]}
        print(f"   📲 {f.name}: {r}")
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
