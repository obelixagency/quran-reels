import json
import re
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
CACHE = ROOT / ".cache"

UA = {"User-Agent": "quran-reels-bot/1.0"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def http_get(url, *, headers=None, params=None, timeout=60, retries=3, stream=False):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers={**UA, **(headers or {})}, params=params,
                             timeout=timeout, stream=stream)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def download(url, dest, *, headers=None):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = http_get(url, headers=headers, stream=True, timeout=120)
    if r.status_code == 404:
        raise FileNotFoundError(url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd))}\n{p.stderr[-3000:]}")
    return p.stdout


def media_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar_num(n):
    return str(n).translate(AR_DIGITS)


_DIACRITICS = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u08D3-\u08FF]")


def skeleton(text):
    """Arabic letters only (no tashkeel / Quranic marks) – used for keyword matching."""
    t = _DIACRITICS.sub("", text)
    t = t.replace("ٱ", "ا").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ة", "ه").replace("ى", "ي").replace("ی", "ي")
    return t
