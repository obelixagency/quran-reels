"""Tests for the engagement lines, first comments and the insights helpers."""
import datetime as dt
import importlib.util
import random
from pathlib import Path
from zoneinfo import ZoneInfo

from src import engage
from src.en import captions as en_captions

BANNED = ["آمين لو", "اكتب «آمين»", "لو بتحب", "Type Ameen", "if you love"]


def _plan(nums):
    return {"surah_name": "الملك", "ayahs": [{"number": n, "text": "x", "tafsir": ""} for n in nums]}


def test_ar_ask_uses_numbers_for_many_ayahs():
    assert "رقمها" in engage.ar_ask("quran", 3)
    assert "كلمة" in engage.ar_ask("quran", 1)


def test_first_lines_two_lines_calm():
    for lang, kinds in (("ar", ["quran", "dua", "hadith", "carousel"]), ("en", ["quran", "recited", "hadith", "dua"])):
        for k in kinds:
            s = engage.first_lines(lang, k, 2, random.Random(1))
            assert len(s.split("\n")) == 2
            assert not any(b in s for b in BANNED)


def test_ar_first_comment_mentions_the_video():
    c = engage.ar_first_comment(_plan([1, 2, 3]))
    assert "الملك" in c and "؟" in c
    c1 = engage.ar_first_comment(_plan([0, 5]))  # 0 = basmala
    assert "الملك" in c1 and "٥" in c1


def test_en_first_comment_specific():
    v = {"surah_number": 2, "ayah_ref": "286", "surah_name": "Al-Baqarah", "collection": "Sahih Muslim"}
    assert "2:286" in engage.en_first_comment("quran", v)
    assert "Sahih Muslim" in engage.en_first_comment("hadith", v)
    assert "Sahih Muslim" in engage.en_first_comment("dua", v)


def test_en_caption_first_line_is_question():
    v = {"verse_text": "t", "surah_number": 2, "ayah_ref": "286", "surah_name": "Al-Baqarah",
         "surah_meaning": "The Cow"}
    caps = en_captions.build("quran", v, "Today's verse", "Save it for the day you need it 🤍")
    for p in ("facebook", "instagram"):
        first = caps[p].split("\n")[0]
        assert first == engage.en_ask("quran")
        assert caps[p].split("\n")[1] == "Save it for the day you need it 🤍"
    assert caps["youtube"].split("\n")[0] == engage.en_ask("quran")
    assert "2:286" in caps["_first_comment"]


def test_en_ctas_have_no_question():
    assert all("?" not in c for c in en_captions.CTAS)


def _insights():
    p = Path(__file__).resolve().parent.parent / "scripts" / "insights.py"
    spec = importlib.util.spec_from_file_location("insights", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_slot_local_handles_winter_time():
    m = _insights()
    cairo = ZoneInfo("Africa/Cairo")
    summer = dt.datetime(2026, 10, 1, 16, 15, tzinfo=dt.timezone.utc).astimezone(cairo)  # UTC+3
    winter = dt.datetime(2026, 11, 10, 16, 15, tzinfo=dt.timezone.utc).astimezone(cairo)  # UTC+2
    assert m.slot_of(summer) == "19:30"
    assert m.slot_of(winter) == "18:30"
    ny = ZoneInfo("America/New_York")
    assert m.slot_of(dt.datetime(2026, 11, 10, 13, 50, tzinfo=dt.timezone.utc).astimezone(ny)) == "09:00"


def test_main_value_prefers_reel_plays():
    m = _insights()
    assert m.main_value("facebook", {"blue_reels_play_count": 5, "post_total_media_view_unique": 9}) == 5
    assert m.main_value("facebook", {"post_total_media_view_unique": 9}) == 9
    assert m.main_value("instagram", {"reach": 3}) == 3
    assert m.main_value("youtube", {}) is None


def test_ar_reel_caption_starts_with_question(monkeypatch):
    from src import captions
    monkeypatch.setattr(captions, "tafsir_spills", lambda plan: False)
    plan = {"surah_name": "الملك", "surah_number": 67, "theme": None,
            "reciter": {"name": "محمد صديق المنشاوي", "key": "minshawi", "hashtag": "#المنشاوي"},
            "ayahs": [{"number": 1, "text": "تبارك", "tafsir": "تفسير"}, {"number": 2, "text": "الذي", "tafsir": "تفسير2"}]}
    for p in ("facebook", "instagram", "youtube", "tiktok"):
        cap = captions.build_caption(plan, p, 5, random.Random(3))
        lines = cap.split("\n")
        assert lines[0] == engage.ar_ask("quran", 2)
        assert lines[1] in engage.AR_SHARE
        assert not any(b in cap for b in BANNED)


def test_ar_post_and_short_captions_start_with_question():
    from src import posts, shorts
    item = {"type": "hadith", "id": "h1"}
    cap = posts.build_caption(item, "نص", "البخاري", 5)
    assert cap.split("\n")[0] == engage.ar_ask("hadith")
    caps = shorts.captions({"type": "dua", "id": "d1"}, "نص", "مسلم")
    assert caps["youtube"].split("\n")[0] == engage.ar_ask("dua")
    assert "آمين" not in "".join(posts.DUA_CTAS)
