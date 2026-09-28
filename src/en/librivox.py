"""English Quran audio for Daily Serenity: LibriVox recording of Pickthall's translation (public domain).

https://librivox.org/the-meaning-of-the-glorious-koran-translated-by-mohammed-marmaduke-pickthall/
Real human volunteer readers – no AI voice. The chapter files are long, so for each passage we:
  1) download the chapter file from the Internet Archive,
  2) get word timings with an offline speech-to-text model (used ONLY to find where each verse is read),
  3) locate the exact Pickthall verse text in those timings (fuzzy match),
  4) cut that part of the human recording.
Transcripts and verse timings are cached in data/en/ so each chapter is processed once.
"""
import difflib
import re

from ..common import CACHE, DATA, download, http_get, load_json, media_duration, run, save_json

ITEM = "meaning_glorious_koran_0810_librivox"
EN = DATA / "en"
TRANSCRIPTS = EN / "transcripts"
TIMES = EN / "verse_times.json"
FILES = EN / "librivox_files.json"


def _norm(w):
    w = w.lower().replace("’", "'")
    w = re.sub(r"[^a-z0-9']", "", w)
    return {"thee": "thee", "o": "oh"}.get(w, w)


def tokens(text):
    return [t for t in (_norm(w) for w in re.split(r"[\s\-–—]+", text)) if t]


def file_map():
    """{surah: [file names]} from the Internet Archive item (cached)."""
    if FILES.exists():
        return {int(k): v for k, v in load_json(FILES).items()}
    meta = http_get(f"https://archive.org/metadata/{ITEM}").json()
    out = {}
    for f in meta["files"]:
        name, title = f.get("name", ""), f.get("title", "")
        if not name.endswith("_64kb.mp3"):
            continue
        m = re.search(r"Surahs?\s*(\d+)\s*(?:[-–]\s*(\d+))?", title)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        for s in range(a, b + 1):
            out.setdefault(s, []).append(name)
    save_json(FILES, {str(k): sorted(v) for k, v in sorted(out.items())})
    return out


def _audio(name):
    return download(f"https://archive.org/download/{ITEM}/{name}", CACHE / "librivox" / name)


_model = None


def transcript(name):
    """[[word, start, end], ...] for one LibriVox file (cached in the repo)."""
    dest = TRANSCRIPTS / (name.replace(".mp3", "") + ".json")
    if dest.exists():
        return load_json(dest)
    global _model
    from faster_whisper import WhisperModel  # installed only in the Daily Serenity workflow
    if _model is None:
        _model = WhisperModel("base.en", device="cpu", compute_type="int8")
    path = _audio(name)
    print(f"  transcribing {name} ({media_duration(path) / 60:.1f} min) …")
    segs, _ = _model.transcribe(str(path), language="en", word_timestamps=True, beam_size=1,
                                vad_filter=True, condition_on_previous_text=False)
    words = [[w.word.strip(), round(w.start, 2), round(w.end, 2)] for s in segs for w in (s.words or [])]
    save_json(dest, words)
    return words


def _locate(verse_tokens, words):
    """Best in-order fuzzy match of the verse tokens inside the transcript → (score, i0, i1)."""
    T = [_norm(w[0]) for w in words]
    n = len(verse_tokens)
    heads = set(verse_tokens[:4])
    best = (0.0, None, None)
    for i in range(len(T)):
        if T[i] not in heads:
            continue
        win = T[i:i + int(n * 1.4) + 3]
        sm = difflib.SequenceMatcher(None, win, verse_tokens, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size]
        matched = sum(b.size for b in blocks)
        score = matched / n
        if score > best[0]:
            j0 = i + blocks[0].a
            j1 = i + blocks[-1].a + blocks[-1].size - 1
            best = (score, j0, j1)
    return best


def verse_segment(surah, ayah, text):
    """(file, start, end, word_times) for one verse, or None if it can't be found reliably."""
    key = f"{surah}:{ayah}"
    cache = load_json(TIMES) if TIMES.exists() else {}
    if key in cache:
        return cache[key] or None
    vt = tokens(text)
    found = None
    for name in file_map().get(surah, []):
        words = transcript(name)
        score, i0, i1 = _locate(vt, words)
        if score >= 0.78 and i0 is not None:
            found = {"file": name, "start": words[i0][1], "end": words[i1][2], "score": round(score, 3),
                     "words": [[w[0], w[1], w[2]] for w in words[i0:i1 + 1]]}
            break
    cache[key] = found or {}
    save_json(TIMES, cache)
    return found


def cut(segments, dest, lead=0.8, tail=1.8):
    """Concatenate verse recordings (with short pauses) into one normalised wav.
    Returns (dest, [shift per verse: output_time = source_time + shift], total)."""
    parts, inputs, t, times = [], [], lead, []
    for k, s in enumerate(segments):
        a, b = max(0.0, s["start"] - 0.15), s["end"] + 0.35
        inputs += ["-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(_audio(s["file"]))]
        parts.append(f"[{k}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"afade=t=in:d=0.08,afade=t=out:st={b - a - 0.2:.2f}:d=0.2,apad=pad_dur=0.6[a{k}]")
        times.append(t - a)
        t += (b - a) + 0.6
    total = t - 0.6 + tail
    chain = "".join(f"[a{k}]" for k in range(len(segments)))
    fc = ";".join(parts) + f";{chain}concat=n={len(segments)}:v=0:a=1,adelay={int(lead * 1000)}:all=1," \
         f"highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,apad,atrim=0:{total:.3f}[out]"
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "[out]", "-ac", "2", str(dest)])
    return dest, times, total
