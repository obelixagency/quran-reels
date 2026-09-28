"""Pre-computes LibriVox timings for every curated passage (run once from the setup workflow).
Passages that can't be matched reliably are reported and will simply be skipped by the daily job."""
from ..common import DATA, load_json
from . import librivox

EN = DATA / "en"


def main():
    verses = load_json(EN / "pickthall.json")["verses"]
    ok, bad = 0, []
    for p in load_json(EN / "passages.json")["items"]:
        good = all(librivox.verse_segment(p["surah"], a, verses[f"{p['surah']}:{a}"])
                   for a in range(p["from"], p["to"] + 1))
        if good:
            ok += 1
        else:
            bad.append(p["id"])
    print(f"passages ready: {ok}, not matched: {len(bad)} {bad}")


if __name__ == "__main__":
    main()
