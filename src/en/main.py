"""Daily Serenity – English reels.

  python -m src.en.main --kind quran            # Quran verse reel (LibriVox human reading, Pickthall text)
  python -m src.en.main --kind sunnah           # hadith or dua (alternating daily)
  add --publish to post, --platforms youtube,instagram to limit, --id to force an item.

Rules from the brief: every post carries its reference + credit line; no verse/hadith/dua repeats within
90 days; no hook twice in a row; no hook+CTA pair within 7 days; only Sahih al-Bukhari / Sahih Muslim.
"""
import argparse
import datetime as dt
import json
import random
import sys
import traceback

from ..backgrounds import get_background
from ..common import DATA, ROOT, load_json, media_duration, save_json
from . import captions, librivox, video

EN = DATA / "en"
OUT = ROOT / "out_en"
HISTORY = ROOT / "history_en.json"
MAX_SECONDS = 58


def load_history():
    return load_json(HISTORY) if HISTORY.exists() else {"posts": []}


def _recent_ids(history, days=90):
    now = dt.datetime.now(dt.timezone.utc)
    return {p["id"] for p in history["posts"]
            if now - dt.datetime.fromisoformat(p["date"]) < dt.timedelta(days=days)}


def _used_backgrounds(history):
    return {p.get("background") for p in history["posts"][-60:]}


def sunnah_kind(history):
    last = [p["kind"] for p in history["posts"] if p["kind"] in ("hadith", "dua")]
    return "dua" if last and last[-1] == "hadith" else "hadith"


# ------------------------------------------------------------------ Quran
def quran_item(history, force=None):
    passages = load_json(EN / "passages.json")["items"]
    verses = load_json(EN / "pickthall.json")["verses"]
    chapters = load_json(EN / "chapters.json")
    recent = _recent_ids(history)
    pool = [p for p in passages if p["id"] == force] if force else [p for p in passages if p["id"] not in recent]
    random.shuffle(pool)
    for p in pool:
        segs, texts = [], []
        for a in range(p["from"], p["to"] + 1):
            t = verses[f"{p['surah']}:{a}"]
            s = librivox.verse_segment(p["surah"], a, t)
            if not s:
                print(f"  ⏭  {p['surah']}:{a} not found in the LibriVox recording – skipping passage")
                break
            segs.append(s)
            texts.append(t)
        else:
            dur = sum(s["end"] - s["start"] + 1.1 for s in segs) + 2.6
            if dur > MAX_SECONDS:
                print(f"  ⏭  {p['id']} too long ({dur:.0f}s)")
                continue
            ch = chapters[str(p["surah"])]
            ref = f"{p['from']}" if p["from"] == p["to"] else f"{p['from']}-{p['to']}"
            return p, segs, texts, {"verse_text": " ".join(texts), "surah_name": ch["name"],
                                    "surah_meaning": ch["meaning"], "surah_number": p["surah"],
                                    "ayah_number": p["from"], "ayah_ref": ref}
    raise RuntimeError("no Quran passage available")


def make_quran(cfg, history, force=None):
    p, segs, texts, v = quran_item(history, force)
    OUT.mkdir(exist_ok=True)
    voice, shifts, total = librivox.cut(segs, OUT / "voice.wav")
    # word timings for the on-screen text: transcript words mapped onto the Pickthall words
    times = []
    for s, shift, text in zip(segs, shifts, texts):
        ws = s["words"]
        n = len(text.split())
        for i in range(n):
            j = min(len(ws) - 1, int(i * len(ws) / n))
            times.append((ws[j][1] + shift, ws[j][2] + shift))
    audio = video.ambient(OUT / "audio.wav", total, voice=voice)
    tl = video.build(label=f"Quran {v['surah_number']}:{v['ayah_ref']}", intro="", text=v["verse_text"],
                     ref=f"Surah {v['surah_name']} · {v['surah_meaning']}",
                     credit="Translation: Marmaduke Pickthall · Recitation: LibriVox (public domain)",
                     times=times, duration=total)
    return p["id"], "quran", v, tl, audio, total


# ------------------------------------------------------------------ hadith / dua
def make_sunnah(cfg, history, kind, force=None):
    items = load_json(EN / ("hadith.json" if kind == "hadith" else "dua.json"))["items"]
    items = [i for i in items if i.get("verified", True)]
    recent = _recent_ids(history)
    pool = [i for i in items if i["id"] == force] if force else [i for i in items if i["id"] not in recent]
    if not pool:
        raise RuntimeError(f"no {kind} available")
    it = random.choice(pool)
    if kind == "hadith":
        v = {"hadith_text": it["en"], "narrator": it["narrator"], "collection": it["collection"],
             "hadith_number": it["number"], "intro": it.get("intro")}
        label, intro = "Hadith", video.for_video(it.get("intro") or "The Prophet ﷺ said:")
        ref = f"Narrated by {it['narrator']} · {it['collection']} {it['number']}"
    else:
        v = {"dua_text": it["en"], "dua_occasion": it.get("occasion", ""), "collection": it["collection"],
             "hadith_number": it["number"], "intro": it.get("intro")}
        occ = it.get("occasion")
        label = "Dua"
        intro = video.for_video(it.get("intro") or (f"A dua from the Prophet ﷺ {occ}:" if occ else "A dua from the Prophet ﷺ:"))
        ref = f"{it['collection']} {it['number']}"
    n = len(it["en"].split())
    total = max(12.0, min(45.0, 5.0 + n / 2.4))
    OUT.mkdir(exist_ok=True)
    audio = video.ambient(OUT / "audio.wav", total)
    tl = video.build(label=label, intro=intro, text=it["en"], ref=ref, credit="Translation: Daily Serenity",
                     duration=total)
    return it["id"], kind, v, tl, audio, total


# ------------------------------------------------------------------ publish
def publish(cfg_en, reel, caps, cover, platforms):
    results = {}
    for name in platforms:
        print(f"🚀 {name} …")
        try:
            if name == "facebook":
                from ..publish_meta import publish_facebook
                results[name] = {"ok": True, **publish_facebook(cfg_en, reel, caps[name], cover=cover)}
            elif name == "instagram":
                from ..publish_meta import publish_instagram
                results[name] = {"ok": True, **publish_instagram(cfg_en, reel, caps[name], cover=cover)}
            elif name == "youtube":
                from ..publish_youtube import publish_youtube
                results[name] = {"ok": True, **publish_youtube(cfg_en, reel, caps[name], caps["_yt_title"],
                                                               caps["_yt_tags"], cover=cover)}
            elif name == "tiktok":
                from ..publish_tiktok import publish_tiktok
                results[name] = {"ok": True, **publish_tiktok(cfg_en, reel, caps[name], cover=cover)}
            print("   ✅", results[name])
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            results[name] = {"ok": False, "error": str(e)[:500]}
    # the same reel is also shared as a Facebook / Instagram story (like the Arabic channels)
    st = cfg_en.get("stories", {"facebook": True, "instagram": True})
    for name, fn in (("facebook", "story_facebook_video"), ("instagram", "story_instagram_video")):
        if st.get(name) and name in platforms:
            try:
                from .. import publish_meta
                results[f"{name}_story"] = {"ok": True, **getattr(publish_meta, fn)(cfg_en, reel)}
            except Exception as e:  # noqa: BLE001
                results[f"{name}_story"] = {"ok": False, "error": str(e)[:300]}
            print(f"   📲 {name} story: {results[f'{name}_story']}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["quran", "sunnah", "hadith", "dua"], default="quran")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--platforms", default="")
    ap.add_argument("--id")
    args = ap.parse_args()

    cfg = load_json(ROOT / "config.json")
    en = cfg.get("en", {})
    cfg_en = {**cfg, "platforms": en.get("platforms", {}), "video": {**cfg["video"], **en.get("video", {})},
              "stories": en.get("stories", {"facebook": True, "instagram": True})}
    history = load_history()

    kind = args.kind if args.kind != "sunnah" else sunnah_kind(history)
    if kind == "quran":
        item_id, kind, v, tl, audio, total = make_quran(cfg_en, history, args.id)
    else:
        item_id, kind, v, tl, audio, total = make_sunnah(cfg_en, history, kind, args.id)

    bg_path, bg_id, credit = get_background(cfg_en, total, _used_backgrounds(history))
    reel = video.render(background=bg_path, timeline=tl, audio=audio, total=total, dest=OUT / "reel.mp4", cfg=cfg_en)
    cov = video.cover(bg_path, tl, OUT / "cover.jpg")
    hook, cta = captions.pick_hook_cta(kind, history["posts"])
    caps = captions.build(kind, v, hook, cta)
    for k, c in caps.items():
        (OUT / f"caption{k if k.startswith('_') else '_' + k}.txt").write_text(c if isinstance(c, str) else json.dumps(c))
    save_json(OUT / "plan.json", {"id": item_id, "kind": kind, "hook": hook, "cta": cta, "values": v,
                                 "background": bg_id, "background_credit": credit})
    print(f"🎬 {kind} {item_id}: {reel} ({media_duration(reel):.1f}s)\n\n{caps['instagram']}")

    if not args.publish:
        return
    platforms = [p for p in (args.platforms.split(",") if args.platforms else cfg_en["platforms"])
                 if p and cfg_en["platforms"].get(p, {}).get("enabled")]
    cover = {"path": str(cov), "ms": int(max(1.0, total - 1.5) * 1000)}
    results = publish(cfg_en, reel, caps, cover, platforms) if platforms else {}
    history["posts"].append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                             "id": item_id, "kind": kind, "hook": hook, "cta": cta, "background": bg_id,
                             "results": results})
    save_json(HISTORY, history)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    main_ok = [r["ok"] for k, r in results.items() if not k.endswith("_story")]
    if main_ok and not any(main_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
