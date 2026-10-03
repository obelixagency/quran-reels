"""الكابشن والهاشتاجات – مبنية على الآيات نفسها (مش متولّدة بالذكاء الاصطناعي عشان مفيش أي خطأ في النص).

الكابشن = جملة افتتاحية حسب موضوع الآيات + نص الآيات من المصدر + السورة وأرقام الآيات + اسم الشيخ
          + التفسير الميسر (مصدر معتمد) + دعوة للمشاركة + الهاشتاجات.
الهاشتاجات = هاشتاج السورة + هاشتاجات الموضوع (من الموضوع المحدد + كلمات مفتاحية في نص الآيات)
             + هاشتاج الشيخ + هاشتاجات عامة. عددها مختلف لكل منصة (إنستجرام حدّه ٥).
"""
import functools
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

    occ_tags = (plan.get("occasion") or {}).get("hashtags", [])[:2]
    out = []
    # always keep: surah, main theme, reciter, general #قرآن_كريم
    must = [ordered[0], THEMES["themes"][themes[0]]["hashtags"][0] if themes else None,
            plan["reciter"]["hashtag"], THEMES["general_hashtags"][0]]
    for tag in [must[0]] + occ_tags + [m for m in must[1:] if m] + ordered:
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


@functools.lru_cache(maxsize=64)
def _tafsir_of(surah, ayah):
    """التفسير الميسر لآية واحدة (Quran.com، واحتياطي alquran.cloud) – "" لو مش متاح."""
    from .quran_source import QURANCOM, _strip_html, http_get
    try:
        return _strip_html(http_get(f"{QURANCOM}/tafsirs/16/by_ayah/{surah}:{ayah}").json()["tafsir"]["text"]).strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        return http_get(f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/ar.muyassar").json()["data"]["text"].strip()
    except Exception:  # noqa: BLE001
        return ""


def _same_text(a, b):
    return bool(a and b) and (a in b or b in a or a[:40] == b[:40])


def tafsir_spills(plan):
    """True لو التفسير الميسر لأول/آخر آية في الريل بيشرح كمان آية برا الريل (التفسير بيجمع كذا آية في نص واحد)
    – ساعتها الكلام هيبان مش متطابق مع الآية، فمنحطوش."""
    s = plan.get("surah")
    nums = [a["number"] for a in plan["ayahs"] if a["number"]]
    if not s or not nums:
        return False
    by = {a["number"]: (a.get("tafsir") or "").strip() for a in plan["ayahs"] if a["number"]}
    lo, hi = min(nums), max(nums)
    if lo > 1 and _same_text(by[lo], _tafsir_of(s, lo - 1)):
        return True
    return _same_text(by[hi], _tafsir_of(s, hi + 1))


def build_caption(plan, platform, n_hashtags, rng=random):
    themes = detect_themes(plan)
    t0 = THEMES["themes"].get(themes[0]) if themes else None
    opener = rng.choice(t0["openers"]) if t0 else "تلاوة تريح القلب 🤍"
    occ = plan.get("occasion")
    if occ:
        opener = occ["opener"]

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
    tafsir = "" if tafsir_spills(plan) else " ".join(parts_t)
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
