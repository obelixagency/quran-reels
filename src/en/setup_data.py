"""Daily Serenity – one-time data setup (runs in GitHub Actions, which has internet).

Downloads, only if missing:
  data/en/pickthall.json   Marmaduke Pickthall translation (1930, public domain) from Tanzil
  data/en/chapters.json    Surah names + meanings (Quran.com API)
  assets/fonts/en/*.ttf    Cormorant Garamond Italic + Jost (SIL Open Font License, Google Fonts)
"""
import re

from ..common import DATA, ROOT, download, http_get, load_json, save_json

EN = DATA / "en"
FONTS = ROOT / "assets" / "fonts" / "en"

FONT_SOURCES = {
    "CormorantGaramond-Italic.ttf": [
        "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
        "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-Italic.ttf",
        "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-MediumItalic.ttf",
    ],
    "CormorantGaramond-SemiBoldItalic.ttf": [
        "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
        "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-SemiBoldItalic.ttf",
    ],
    "Jost.ttf": [
        "https://github.com/google/fonts/raw/main/ofl/jost/Jost%5Bwght%5D.ttf",
        "https://github.com/google/fonts/raw/main/ofl/jost/Jost-Regular.ttf",
    ],
}


def fonts():
    for name, urls in FONT_SOURCES.items():
        dest = FONTS / name
        if dest.exists():
            continue
        for u in urls:
            try:
                download(u, dest)
                print("font", name, "<-", u)
                break
            except Exception as e:  # noqa: BLE001
                print("  font source failed", u, e)
        else:
            raise RuntimeError(f"could not download font {name}")


def pickthall():
    dest = EN / "pickthall.json"
    if dest.exists():
        return
    verses = {}
    try:
        r = http_get("https://tanzil.net/trans/?transID=en.pickthall&type=txt-2", timeout=120)
        for line in r.text.splitlines():
            m = re.match(r"^(\d+)\|(\d+)\|(.*)$", line.strip())
            if m:
                verses[f"{int(m.group(1))}:{int(m.group(2))}"] = m.group(3).strip()
        src = "Tanzil (tanzil.net) – en.pickthall"
    except Exception as e:  # noqa: BLE001
        print("tanzil failed:", e)
    if len(verses) < 6236:
        verses, src = {}, "Quran.com API – translation 19 (M. Pickthall)"
        for ch in range(1, 115):
            page = 1
            while True:
                r = http_get(f"https://api.quran.com/api/v4/verses/by_chapter/{ch}",
                             params={"translations": 19, "per_page": 50, "page": page, "fields": "verse_key"})
                j = r.json()
                for v in j["verses"]:
                    t = re.sub(r"<[^>]+>", "", v["translations"][0]["text"])
                    verses[v["verse_key"]] = t.strip()
                if not j["pagination"].get("next_page"):
                    break
                page += 1
    assert len(verses) >= 6236, len(verses)
    save_json(dest, {"_source": src, "_license": "Public domain (Marmaduke Pickthall, 1930). Text used exactly as published.",
                     "verses": verses})
    print("pickthall verses:", len(verses), "from", src)


def chapters():
    dest = EN / "chapters.json"
    if dest.exists():
        return
    r = http_get("https://api.quran.com/api/v4/chapters", params={"language": "en"})
    out = {str(c["id"]): {"name": c["name_simple"], "meaning": c["translated_name"]["name"],
                          "verses": c["verses_count"]} for c in r.json()["chapters"]}
    save_json(dest, out)
    print("chapters:", len(out))


def main():
    EN.mkdir(parents=True, exist_ok=True)
    fonts()
    pickthall()
    chapters()


if __name__ == "__main__":
    main()
