"""Daily Serenity – Quran reel with an Arabic recitation (the same reciters as the Arabic channel)
and Pickthall's English translation on screen.

The Arabic words appear one by one in sync with the reciter (Quran.com word timings, same as the
Arabic reels); the English translation of that ayah sits under it. Everything else (captions,
hashtags, publishing) is the English channel's.
"""
import random

from PIL import Image, ImageDraw, ImageFilter

from ..common import DATA, ar_num, load_json
from ..main import build_plan, pick_reciter
from ..render import WHITE, _fit, _line_layer, build_audio
from .video import GOLD_L, W, H, _spaced, _wrap, sans, serif

RECITERS_EN = {
    "husary": "Sheikh Mahmoud Khalil Al-Husary",
    "minshawi": "Sheikh Mohamed Siddiq Al-Minshawi",
    "abdulbasit": "Sheikh Abdul Basit Abdus Samad",
    "tablawi": "Sheikh Mohamed Al-Tablawi",
    "alafasy": "Sheikh Mishary Rashid Alafasy",
    "sudais": "Sheikh Abdul Rahman Al-Sudais",
    "shuraim": "Sheikh Saud Al-Shuraim",
    "maher": "Sheikh Maher Al-Muaiqly",
}


def build_card(*, words, ayah_no, en_text, label, reciter_en):
    """Same shape as src.render.build_card ({"base","white","gold"}) so the Arabic Timeline animates it:
    Arabic words written one by one + the English translation (static on the card)."""
    tokens = list(words) + ([f"۝{ar_num(ayah_no)}"] if ayah_no else [])
    font, lines, line_h = _fit(tokens, W - 190, int(H * 0.27), start=92, minimum=40)

    # English translation block
    en_words = en_text.split()
    size = 48
    while True:
        f_en = serif(size)
        en_lines = [" ".join(l) for l in _wrap(en_words, f_en, W - 220)]
        en_lh = int(size * 1.32)
        if len(en_lines) * en_lh <= H * 0.24 or size <= 30:
            break
        size -= 2

    f_label, f_ref = sans(32, 500), sans(30, 420)
    ar_h = len(lines) * line_h
    en_h = len(en_lines) * en_lh if en_lines else 0
    block = 60 + ar_h + 64 + en_h + 40 + 44
    top = int(H * 0.45) - block // 2
    cx = W // 2

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((58, top - 60, W - 58, top + block + 50), radius=46,
                                            fill=(20, 28, 24, 150))
    base = panel.filter(ImageFilter.GaussianBlur(22))
    d = ImageDraw.Draw(base)
    _spaced(d, (cx, top + 4), label.upper(), f_label, GOLD_L, 9)

    ar_top = top + 60
    y = ar_top + ar_h + 64
    d.line((cx - 110, y - 26, cx + 110, y - 26), fill=GOLD_L[:3] + (140,), width=2)
    for k, ln in enumerate(en_lines):
        cy = y + k * en_lh + en_lh // 2
        d.text((cx + 2, cy + 2), ln, font=f_en, fill=(0, 0, 0, 150), anchor="mm")
        d.text((cx, cy), ln, font=f_en, fill=(243, 235, 221, 245), anchor="mm")
    y += en_h + 40
    d.text((cx, y), reciter_en, font=f_ref, fill=GOLD_L, anchor="mm")
    _spaced(d, (cx, H - 250), "DAILY SERENITY", sans(30, 500), (243, 235, 221, 200), 12)

    # Arabic words as sprites (right → left), exactly like the Arabic reels
    white = []
    space = font.getlength(" ")
    for li, toks in enumerate(lines):
        cy = ar_top + li * line_h + line_h // 2
        text = " ".join(toks)
        lw = font.getlength(text, direction="rtl")
        widths = [font.getlength(t, direction="rtl") for t in toks]
        f = lw / (sum(widths) + space * (len(toks) - 1))
        right = cx + lw / 2
        layer = _line_layer(W, H, text, font, cx, cy, WHITE)
        y0, y1 = int(cy - line_h * 0.62), int(cy + line_h * 0.62)
        cum = 0.0
        for j, w in enumerate(widths):
            r = right - cum * f + (space * f / 2 if j else 30)
            left = right - (cum + w) * f - (space * f / 2 if j < len(toks) - 1 else 30)
            box = (max(0, int(left)), max(0, y0), min(W, int(r + 1)), min(H, y1))
            white.append((layer.crop(box), box[0], box[1]))
            cum += w + space
    return {"base": base, "white": white, "gold": [], "n_tokens": len(tokens)}


def make(cfg_en, history, recent_ids, force=None, reciter_key=None, out=None):
    """Returns (item_id, values, timeline, audio_path, total, reciter)."""
    from ..render import Timeline
    passages = load_json(DATA / "en" / "passages.json")["items"]
    verses = load_json(DATA / "en" / "pickthall.json")["verses"]
    chapters = load_json(DATA / "en" / "chapters.json")
    surahs = load_json(DATA / "surahs.json")
    reciters = load_json(DATA / "reciters.json")["reciters"]
    reciter = pick_reciter(reciters, {"posts": [{"reciter": p.get("reciter")} for p in history["posts"]
                                                if p.get("kind") == "recited"]}, reciter_key)

    pool = [p for p in passages if p["id"] == force] if force else [p for p in passages if p["id"] not in recent_ids]
    random.shuffle(pool)
    cfg_plan = {**cfg_en, "max_seconds": 58}
    for p in pool[:12]:
        try:
            plan = build_plan(cfg_plan, p, reciter, surahs)
        except Exception as e:  # noqa: BLE001
            print(f"  {p['id']} failed: {e}")
            continue
        if not plan:
            continue
        ayahs = [a for a in plan["ayahs"]]
        nums = [a["number"] for a in ayahs if a["number"]]
        s = p["surah"]
        ch = chapters[str(s)]
        ref = f"{nums[0]}" if len(nums) == 1 else f"{nums[0]}-{nums[-1]}"
        audio, times, total = build_audio([a["audio"] for a in ayahs], out / "voice.wav")
        cards = []
        for i, a in enumerate(ayahs):
            if a["number"]:
                en = verses[f"{s}:{a['number']}"]
            else:
                en = "In the name of Allah, the Beneficent, the Merciful."
            card = build_card(words=a["words"], ayah_no=a["number"], en_text=en,
                              label=f"Quran {s}:{a['number']}" if a["number"] else f"Surah {ch['name']}",
                              reciter_en=f"Recited by {RECITERS_EN.get(reciter['key'], reciter['key'])}")
            start = times[i][0]
            words = [(start + ws, start + we) for ws, we in a["timings"]]
            if a["number"]:
                last = words[-1][1] if words else start
                words.append((last - 0.05, last + 0.35))
            end = times[i + 1][0] - 0.15 if i + 1 < len(times) else total - 0.15
            cards.append({"card": card, "window": (max(0.0, start - 0.15 - (0.25 if i == 0 else 0)), end),
                          "words": words})
        en_text = " ".join(verses[f"{s}:{n}"] for n in nums)
        v = {"verse_text": en_text, "surah_name": ch["name"], "surah_meaning": ch["meaning"], "surah_number": s,
             "ayah_number": nums[0], "ayah_ref": ref,
             "credit": f"Recitation: {RECITERS_EN.get(reciter['key'], reciter['key'])} · "
                       f"Translation: Marmaduke Pickthall (public domain)"}
        return p["id"], v, Timeline(cards, "write", total), audio, total, reciter["key"]
    raise RuntimeError("no recited passage fits")
