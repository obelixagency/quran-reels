"""التفاعل: أول سطرين في الكابشن + أول كومنت.

النبرة هادية ومن غير أي ضغط ديني لجمع التفاعل (مفيش «اكتب آمين لو…» ولا «لو بتحب النبي اكتب…»).
السطر الأول = سؤال سهل يترد عليه بكلمة أو رقم ويخص الفيديو نفسه، والتاني = دعوة لحفظ أو مشاركة.
أول كومنت = سؤال محدد عن الفيديو نفسه (السورة/الآية/المصدر)، مش جملة عامة.
"""
import random

from .common import ar_num

AR_SHARE = ["احفظها تفكّرك، وابعتها لحد بتحبه 🌿", "ابعتها لحد محتاج يسمعها النهارده 🤍",
            "احفظ الريل ده وارجعله وقت ما تحتاجه 🌙", "شاركها مع حد غالي عليك 🤍"]
EN_SHARE = ["Save it for the day you need it 🤍", "Send this to someone you love 🌿",
            "Share it with a friend who needs it today 🤍", "Save this and come back to it tonight 🌙"]


def ar_ask(kind, n_ayahs=1):
    if kind in ("dua", "quran_dua"):
        return "إمتى بتحب تدعي بالدعاء ده… الصبح ولا بالليل؟ 🤲"
    if kind in ("hadith", "athar"):
        return "إيه الكلمة اللي وقفت عندها في الحديث؟ اكتبها 🤍"
    if kind == "carousel":
        return "أنهي صورة فيهم أقرب لقلبك؟ اكتب رقمها 🤍"
    if n_ayahs > 1:
        return "أنهي آية وقفت عندها؟ اكتب رقمها 🤍"
    return "كلمة واحدة وصلتلك من الآية… اكتبها 🤍"


def en_ask(kind):
    kind = "quran" if kind == "recited" else kind
    if kind == "dua":
        return "Morning or night — when will you say this dua? 🌙"
    if kind == "hadith":
        return "Which part of this hadith will you carry today? One word is enough 🤍"
    if kind == "carousel":
        return "Which slide is closest to your heart? Reply with its number 🤍"
    return "Which word stayed with you? Reply with one word 🤍"


def first_lines(lang, kind, n_ayahs=1, rng=random):
    if lang == "ar":
        return f"{ar_ask(kind, n_ayahs)}\n{rng.choice(AR_SHARE)}"
    return f"{en_ask(kind)}\n{rng.choice(EN_SHARE)}"


def ar_first_comment(plan):
    nums = [a["number"] for a in plan["ayahs"] if a["number"]]
    s = plan["surah_name"]
    if len(nums) > 1:
        return (f"سورة {s} من الآية {ar_num(nums[0])} للآية {ar_num(nums[-1])}: "
                f"أنهي آية فيهم حسّيت إنها بتكلمك إنت النهارده؟ 🤍")
    return f"الآية {ar_num(nums[0])} من سورة {s}: إيه أكتر كلمة فيها لمست قلبك؟ 🤍"


def en_first_comment(kind, v):
    kind = "quran" if kind == "recited" else kind
    if kind == "quran":
        return (f"Quran {v['surah_number']}:{v['ayah_ref']} (Surah {v['surah_name']}) — "
                f"which word in this verse speaks to you most today? 🤍")
    if kind == "hadith":
        return f"This hadith is from {v['collection']} — what is one small way you could live it today? 🌿"
    return f"This dua is from {v['collection']} — who will you include in it today? 🤲"
