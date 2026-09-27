"""الكابشن والهاشتاجات – مبنية على الآيات نفسها (مش متولّدة بالذكاء الاصطناعي عشان مفيش أي خطأ في النص).

الكابشن = جملة افتتاحية حسب موضوع الآيات + نص الآيات من المصدر + السورة وأرقام الآيات + اسم الشيخ
          + التفسير الميسر (مصدر معتمد) + دعوة للمشاركة + الهاشتاجات.
الهاشتاجات = هاشتاج السورة + هاشتاجات الموضوع (من الموضوع المحدد + كلمات مفتاحية في نص الآيات)
             + هاشتاج الشيخ + هاشتاجات عامة. عددها مختلف لكل منصة (إنستجرام حدّه ٥).
"""
import random

from .common import DATA, ar_num, load_json, skeleton

THEMES = load_json(DATA / "themes.json")

LIMITS = {"instagram": 2200, "facebook": 5000, "tiktok": 2200, "youtube": 4900}
TAFSIR_MAX = {"instagram": 700, "facebook": 1200, "tiktok": 450, "youtube": 1200}


def surah_hashtag(name):
    return "#سورة_" + name.replace(" ", "_")


def detect_themes(plan):
    found = [plan["theme"]] if plan.get("theme") else []
    skel = skeleton(" ".join(a["text"] for a in plan["ayahs"] if a["number"]))
    for key, t in THEMES["themes"].items():
        if key not in found and any(k and k in skel for k in t["keywords"]):
            found.append(key)
    return found


def hashtags(plan, count):
    themes = detect_themes(plan)
    ordered = [surah_hashtag(plan["surah_name"])]
    # first hashtag of each detected theme, then the 2nd ones
    for i in range(2):
        for key in themes:
            tags = THEMES["themes"][key]["hashtags"]
            if i < len(tags):
                ordered.append(tags[i])
    ordered.append(plan["reciter"]["hashtag"])
    ordered += THEMES["general_hashtags"]

    out = []
    # always keep: surah, main theme, reciter, general #قرآن_كريم
    must = [ordered[0], THEMES["themes"][themes[0]]["hashtags"][0] if themes else None,
            plan["reciter"]["hashtag"], THEMES["general_hashtags"][0]]
    for tag in [m for m in must if m] + ordered:
        if tag not in out:
            out.append(tag)
    return out[:count]


def _ayah_range(plan):
    nums = [a["number"] for a in plan["ayahs"] if a["number"]]
    if len(nums) == 1:
        return f"الآية {ar_num(nums[0])}"
    return f"الآيات {ar_num(nums[0])} – {ar_num(nums[-1])}"


def _cut(text, n):
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut + " …"


def build_caption(plan, platform, n_hashtags, rng=random):
    themes = detect_themes(plan)
    t0 = THEMES["themes"].get(themes[0]) if themes else None
    opener = rng.choice(t0["openers"]) if t0 else "تلاوة تريح القلب 🤍"

    basmala = next((a["text"] for a in plan["ayahs"] if not a["number"]), "")
    ayat = " ".join(f"{a['text']} ({ar_num(a['number'])})" for a in plan["ayahs"] if a["number"])
    parts_t = []  # التفسير الميسر أحيانًا بيجمع كذا آية في نص واحد → منكررش
    for a in plan["ayahs"]:
        t = (a.get("tafsir") or "").strip()
        if not (a["number"] and t):
            continue
        dup = next((i for i, x in enumerate(parts_t) if t in x or x in t or t[:40] == x[:40]), None)
        if dup is None:
            parts_t.append(t)
        elif len(t) > len(parts_t[dup]):
            parts_t[dup] = t
    tafsir = " ".join(parts_t)
    tags = " ".join(hashtags(plan, n_hashtags))
    cta = rng.choice(THEMES["ctas"])

    def assemble(taf_len):
        parts = [
            opener,
            (f"{basmala}\n" if basmala else "") + f"﴿ {ayat} ﴾",
            f"📖 سورة {plan['surah_name']} | {_ayah_range(plan)}\n🎙️ بصوت الشيخ {plan['reciter']['name']}",
        ]
        if tafsir and taf_len > 0:
            parts.append(f"💡 التفسير الميسر:\n{_cut(tafsir, taf_len)}")
        parts += [cta, tags]
        return "\n\n".join(parts)

    taf_len = TAFSIR_MAX[platform]
    cap = assemble(taf_len)
    while len(cap) > LIMITS[platform] and taf_len > 0:
        taf_len -= 100
        cap = assemble(taf_len)
    return cap


def youtube_title(plan):
    """عنوان قصير (أقل من ١٠٠ حرف) + #Shorts"""
    nums = [a["number"] for a in plan["ayahs"] if a["number"]]
    rng_txt = f"الآية {ar_num(nums[0])}" if len(nums) == 1 else f"الآيات {ar_num(nums[0])}-{ar_num(nums[-1])}"
    title = f"سورة {plan['surah_name']} ({rng_txt}) | الشيخ {plan['reciter']['name']} #Shorts"
    return title[:100]


def youtube_tags(plan):
    tags = [t.lstrip("#").replace("_", " ") for t in hashtags(plan, 12)]
    return list(dict.fromkeys(tags + ["قرآن", "تلاوة", "quran", "shorts"]))
