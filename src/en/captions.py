"""Daily Serenity – titles, captions, hashtags and tags, exactly as in the project brief."""
import datetime as dt
import random

HOOKS = {
    "quran": ["A verse to calm your heart today", "Pause for a minute and reflect", "Read this slowly",
              "Words that have brought peace for centuries", "Take a breath before you scroll", "Today's verse",
              "Let this one sink in"],
    "hadith": ["Words of the Prophet ﷺ for your day", "A timeless lesson from the Prophet ﷺ", "Read this slowly",
               "A reminder your heart needed", "Wisdom from the Prophet ﷺ"],
    "dua": ["A dua to keep close to your heart", "Say this today", "A dua from the Prophet ﷺ",
            "Save this dua for when you need it", "Words to ask Allah with"],
}
CTAS = ["Share it with someone who needs it 🌿", "Save it for the day you need it 🤍", "Follow for a daily reminder 🌙",
        "Which word stood out to you? Tell us below 👇", "Send this to a friend 🤍"]
HASHTAGS = {
    "quran": ["#DailySerenity", "#QuranInEnglish", "#QuranVerse", "#QuranQuotes", "#IslamicReminders", "#Islam", "#Muslim", "#Faith"],
    "hadith": ["#DailySerenity", "#Hadith", "#Sunnah", "#ProphetMuhammad", "#IslamicReminders", "#Islam", "#Muslim", "#Faith"],
    "dua": ["#DailySerenity", "#Dua", "#Sunnah", "#DailyDua", "#IslamicReminders", "#Islam", "#Muslim", "#Faith"],
}
YT_TAGS = {
    "quran": ["Daily Serenity", "Quran in English", "Quran Verse of the Day", "Quran English Translation", "Quran Shorts",
              "Surah {surah_name}", "Islamic Reminder", "Words of Allah"],
    "hadith": ["Daily Serenity", "Hadith", "Hadith in English", "Sahih Hadith", "Sunnah", "Prophet Muhammad",
               "{collection}", "Islamic Reminder"],
    "dua": ["Daily Serenity", "Dua", "Dua in English", "Daily Dua", "Prophetic Dua", "Sunnah", "Islamic Reminder"],
}
CREDIT = {"quran": "Translation: Marmaduke Pickthall (public domain)",
          "hadith": "Translation: Daily Serenity", "dua": "Translation: Daily Serenity"}


def pick_hook_cta(kind, history, rng=random):
    """No hook twice in a row; no hook+CTA combination repeated within 7 days."""
    now = dt.datetime.now(dt.timezone.utc)
    recent = [h for h in history if h.get("hook")]
    last_hook = recent[-1]["hook"] if recent else None
    week = {(h["hook"], h.get("cta")) for h in recent
            if now - dt.datetime.fromisoformat(h["date"]) < dt.timedelta(days=7)}
    combos = [(h, c) for h in HOOKS[kind] for c in CTAS if h != last_hook and (h, c) not in week]
    if not combos:
        combos = [(h, c) for h in HOOKS[kind] for c in CTAS if h != last_hook]
    return rng.choice(combos)


def body(kind, v):
    if kind == "quran":
        return (f"\"{v['verse_text']}\"\n\n📖 Quran {v['surah_number']}:{v['ayah_ref']} | "
                f"Surah {v['surah_name']} ({v['surah_meaning']})")
    if kind == "hadith":
        intro = v.get("intro") or "The Prophet ﷺ said:"
        return f"{intro}\n\"{v['hadith_text']}\"\n\n📚 Narrated by {v['narrator']} | {v['collection']} {v['hadith_number']}"
    occ = v.get("dua_occasion") or ""
    intro = v.get("intro") or (f"A dua from the Prophet ﷺ {occ}:" if occ else "A dua from the Prophet ﷺ:")
    return f"{intro}\n\"{v['dua_text']}\"\n\n📚 {v['collection']} {v['hadith_number']}"


def build(kind, v, hook, cta):
    b = body(kind, v)
    tags = HASHTAGS[kind]
    credit = CREDIT[kind]
    if kind == "quran":
        yt_title = f"{hook} | Quran {v['surah_number']}:{v['ayah_ref']} #shorts"
    elif kind == "hadith":
        yt_title = f"{hook} | {v['collection']} #shorts"
    else:
        yt_title = f"{hook} | Dua from the Sunnah #shorts"
    if len(yt_title) > 100:  # hook + reference only, never over 100 characters
        yt_title = yt_title[:100]
    yt_desc = (f"{b}\n\nA new reminder every day. Subscribe to Daily Serenity for your daily moment of peace 🌿\n\n"
               f"{credit}\n\n{' '.join(tags[:4] + ['#shorts'])}")
    meta = f"{hook} 🤍\n\n{b}\n\n{cta}\n\n{credit}\n\n{' '.join(tags)}"
    tiktok = f"{hook} 🌿 {b} {cta}\n{' '.join(tags[:4] + ['#fyp'])}"
    yt_tags = [t.format(surah_name=v.get("surah_name", ""), collection=v.get("collection", "")) for t in YT_TAGS[kind]]
    return {"facebook": meta, "instagram": meta, "tiktok": tiktok[:2200], "youtube": yt_desc,
            "_yt_title": yt_title, "_yt_tags": yt_tags}
