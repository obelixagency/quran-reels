"""نص الآيات والتفسير والتلاوة وتوقيت كل كلمة – كلها من مصادر موثوقة (لا يوجد أي توليد بالذكاء الاصطناعي).

المصدر الأساسي: Quran.com API
  - النص العثماني (text_uthmani)
  - التلاوة آية بآية + توقيت كل كلمة داخل التلاوة (segments) → عشان الكلمات تتكتب مع صوت الشيخ بالظبط
  - التفسير الميسر (tafsir id 16)
الاحتياطي: alquran.cloud (نص Tanzil + التفسير الميسر) و everyayah.com (التلاوة) + توقيت تقديري من الصوت.
"""
import html
import re
import subprocess

from .common import CACHE, download, http_get, load_json, media_duration, save_json, skeleton

BASMALA_SKEL = "بسم الله الرحمن الرحيم"
QURANCOM = "https://api.quran.com/api/v4"
_HAS_LETTER = re.compile(r"[ء-يٱ-ۓۺ-ۿ]")


# ---------------------------------------------------------------- text helpers
def _clean(text, surah, ayah):
    text = text.replace("﻿", "").replace("۞", "").strip()
    if ayah == 1 and surah not in (1, 9):
        words = text.split()
        if len(words) > 4 and skeleton(" ".join(words[:4])) == BASMALA_SKEL:
            text = " ".join(words[4:])
    return re.sub(r"\s+", " ", text).strip()


def words_of(text):
    """Split an ayah into words; standalone waqf marks (ۗ ۚ ۖ …) stick to the previous word."""
    out = []
    for tok in text.split():
        if out and not _HAS_LETTER.search(tok):
            out[-1] = f"{out[-1]} {tok}"
        else:
            out.append(tok)
    return out


def _strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _abs_url(url):
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith("http"):
        return "https://verses.quran.com/" + url.lstrip("/")
    return url


# ---------------------------------------------------------------- timing
def _voiced_intervals(path, total):
    """Speech intervals of an mp3 using ffmpeg silencedetect."""
    p = run_stderr(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                    "silencedetect=noise=-38dB:d=0.18", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p)]
    silences = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else total
        silences.append((s, e))
    voiced, t = [], 0.0
    for s, e in silences:
        if s > t + 0.05:
            voiced.append((t, s))
        t = max(t, e)
    if total > t + 0.05:
        voiced.append((t, total))
    return voiced or [(0.0, total)]


def run_stderr(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stderr


def estimate_timings(path, words, duration):
    """No word timings available → spread words over the voiced parts of the audio by letter count."""
    voiced = _voiced_intervals(path, duration)
    total_v = sum(b - a for a, b in voiced)
    weights = []
    for w in words:
        sk = skeleton(w).replace(" ", "")
        weights.append(max(1.0, len(sk) + 1.5 * w.count("ٓ") + 0.6))
    tot_w = sum(weights)

    def at(frac):  # map a fraction of voiced time → absolute seconds
        target = frac * total_v
        for a, b in voiced:
            if target <= b - a:
                return a + target
            target -= b - a
        return voiced[-1][1]

    out, cum = [], 0.0
    for w in weights:
        out.append((at(cum / tot_w), at((cum + w) / tot_w)))
        cum += w
    return out


def timings_from_segments(segments, n_words):
    """Quran.com segments: [idx, word_number(1-based), start_ms, end_ms] (older format: [word, start, end])."""
    t = [None] * n_words
    for seg in segments or []:
        if len(seg) < 3:
            continue
        w, s, e = int(seg[-3]), seg[-2], seg[-1]
        if 1 <= w <= n_words and t[w - 1] is None:
            t[w - 1] = (s / 1000.0, e / 1000.0)
    known = sum(x is not None for x in t)
    if known < max(1, int(n_words * 0.7)):
        return None
    # fill small gaps by interpolation
    for i in range(n_words):
        if t[i] is None:
            prev_end = t[i - 1][1] if i and t[i - 1] else 0.0
            nxt = next((t[j][0] for j in range(i + 1, n_words) if t[j]), prev_end + 0.4)
            t[i] = (prev_end, max(prev_end + 0.1, nxt))
    return t


# ---------------------------------------------------------------- fetching
def _from_qurancom(reciter, surah, ayah):
    key = f"{surah}:{ayah}"
    v = http_get(f"{QURANCOM}/verses/by_key/{key}",
                 params={"fields": "text_uthmani", "audio": reciter["qurancom_id"]}).json()["verse"]
    audio = v.get("audio") or {}
    tafsir = ""
    try:
        tafsir = _strip_html(http_get(f"{QURANCOM}/tafsirs/16/by_ayah/{key}").json()["tafsir"]["text"])
    except Exception:  # noqa: BLE001
        pass
    return {"text": v["text_uthmani"], "tafsir": tafsir,
            "audio_url": _abs_url(audio["url"]) if audio.get("url") else None,
            "segments": audio.get("segments")}


def _from_fallback(reciter, surah, ayah):
    r = http_get(f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/editions/quran-uthmani,ar.muyassar")
    data = r.json()["data"]
    url = None
    if reciter.get("everyayah"):
        url = f"https://everyayah.com/data/{reciter['everyayah']}/{surah:03d}{ayah:03d}.mp3"
    return {"text": data[0]["text"], "tafsir": data[1]["text"], "audio_url": url, "segments": None}


def fetch_verse(reciter, surah, ayah):
    """Returns {"text","tafsir","audio"(path),"words","timings"[(start,end) per word],"timing_source"}"""
    meta_path = CACHE / "verse" / reciter["key"] / f"{surah:03d}{ayah:03d}.json"
    if meta_path.exists():
        meta = load_json(meta_path)
    else:
        meta = None
        if reciter.get("qurancom_id"):
            try:
                meta = _from_qurancom(reciter, surah, ayah)
            except Exception as e:  # noqa: BLE001
                print(f"  quran.com failed ({e}); using fallback sources")
        if not meta or not meta.get("audio_url"):
            fb = _from_fallback(reciter, surah, ayah)
            if meta:  # نص quran.com + صوت everyayah → التوقيت هيتحسب تقديريًا
                meta.update(audio_url=fb["audio_url"], segments=None)
            else:
                meta = fb
        save_json(meta_path, meta)

    audio = CACHE / "audio" / reciter["key"] / f"{surah:03d}{ayah:03d}.mp3"
    download(meta["audio_url"], audio)

    text = _clean(meta["text"], surah, ayah)
    words = words_of(text)
    duration = media_duration(audio)
    timings = timings_from_segments(meta.get("segments"), len(words))
    source = "quran.com"
    if timings is None:
        timings = estimate_timings(audio, words, duration)
        source = "estimated"
    timings = [(max(0.0, min(s, duration)), max(0.0, min(e, duration))) for s, e in timings]
    return {"text": text, "tafsir": (meta.get("tafsir") or "").strip(), "audio": audio,
            "words": words, "timings": timings, "timing_source": source, "duration": duration}
