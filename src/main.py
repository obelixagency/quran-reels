"""تشغيل كامل: اختيار الآيات → تحميل النص والتلاوة → خلفية → تركيب الريل → كابشن وهاشتاجات → نشر.

أمثلة:
  python -m src.main                       # يولّد ريل في out/ بدون نشر (للتجربة)
  python -m src.main --publish             # يولّد وينشر على كل المنصات المفعّلة في config.json
  python -m src.main --publish --platforms facebook,instagram
  python -m src.main --passage raad-28 --reciter minshawi
"""
import argparse
import datetime as dt
import json
import random
import shutil
import sys
import traceback

from . import captions
from .backgrounds import get_background
from .common import DATA, OUT, ROOT, load_json, media_duration, save_json
from .quran_source import fetch_verse
from .render import GAP, LEAD, TAIL, Timeline, build_audio, build_card, compose

HISTORY = ROOT / "history.json"


def load_history():
    return load_json(HISTORY) if HISTORY.exists() else {"posts": []}


def pick_reciter(reciters, history, forced=None):
    enabled = [r for r in reciters if r.get("enabled")]
    if forced:
        return next(r for r in reciters if r["key"] == forced)
    last_used = {}
    for i, p in enumerate(history["posts"]):
        last_used[p.get("reciter")] = i
    enabled.sort(key=lambda r: (last_used.get(r["key"], -1), random.random()))
    return enabled[0]


def candidate_passages(cfg, passages, surahs, history, forced=None):
    if forced:
        return [next(p for p in passages if p["id"] == forced)]
    if cfg.get("selection_mode") == "random":
        out = []
        weights = [s["ayahs"] for s in surahs]
        for _ in range(15):
            s = random.choices(surahs, weights=weights)[0]
            a = random.randint(1, s["ayahs"])
            out.append({"id": f"rand-{s['number']}-{a}", "surah": s["number"], "from": a,
                        "to": min(s["ayahs"], a + 10), "theme": None})
        return out
    recent = {p["passage_id"] for p in history["posts"][-cfg.get("avoid_repeat_last", 40):]}
    fresh = [p for p in passages if p["id"] not in recent] or passages
    random.shuffle(fresh)
    return fresh


def build_plan(cfg, passage, reciter, surahs):
    budget = cfg["max_seconds"] - LEAD - TAIL
    s = passage["surah"]
    surah_name = surahs[s - 1]["name"]
    segments = []

    if passage["from"] == 1 and s not in (1, 9):  # البسملة قبل أول آية في السورة
        b = fetch_verse(reciter, 1, 1)
        segments.append({"number": None, **b})

    used = sum(x["duration"] for x in segments)
    for a in range(passage["from"], passage["to"] + 1):
        v = fetch_verse(reciter, s, a)
        extra = v["duration"] + (GAP if segments else 0)
        if used + extra > budget and segments and not any(x["number"] for x in segments):
            segments, used, extra = [], 0, v["duration"]  # البسملة + أول آية أطول من المسموح → نشيل البسملة
        if used + extra > budget:
            break
        segments.append({"number": a, **v})
        used += extra

    if not any(x["number"] for x in segments):
        return None
    return {"passage_id": passage["id"], "surah": s, "surah_name": surah_name, "theme": passage.get("theme"),
            "reciter": reciter, "ayahs": segments}


def generate(cfg, args, history):
    reciters = load_json(DATA / "reciters.json")["reciters"]
    passages = load_json(DATA / "passages.json")
    surahs = load_json(DATA / "surahs.json")

    reciter = pick_reciter(reciters, history, args.reciter)
    print(f"🎙️  Reciter: {reciter['name']}")

    plan = None
    for p in candidate_passages(cfg, passages, surahs, history, args.passage)[:12]:
        print(f"📖 Trying {p['id']} ({p['surah']}:{p['from']}-{p['to']})")
        try:
            plan = build_plan(cfg, p, reciter, surahs)
        except Exception as e:  # noqa: BLE001
            print(f"   failed: {e}")
            plan = None
        if plan:
            break
        print("   too long for the time limit – next")
    if not plan:
        raise SystemExit("Could not build any passage within the time limit")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    audio, times, total = build_audio([a["audio"] for a in plan["ayahs"]], OUT / "audio.wav")
    print(f"⏱️  Duration: {total:.1f}s")

    used_bg = {p.get("background") for p in history["posts"][-60:]}
    bg, bg_id, credit = get_background(cfg, total, used_bg)
    print(f"🌊 Background: {bg_id}")

    v = cfg["video"]
    style = v.get("text_style", "write")
    cards = []
    for i, a in enumerate(plan["ayahs"]):
        card = build_card(words=a["words"], ayah_no=a["number"], surah_name=plan["surah_name"],
                          reciter_name=reciter["name"], style=style, W=v["width"], H=v["height"],
                          watermark=v.get("watermark", ""))
        start = times[i][0]
        words = [(start + ws, start + we) for ws, we in a["timings"]]
        if a["number"]:  # علامة نهاية الآية ورقمها تظهر بعد آخر كلمة
            last = words[-1][1] if words else start
            words.append((last - 0.05, last + 0.35))
        end = times[i + 1][0] - 0.15 if i + 1 < len(times) else total - 0.15
        cards.append({"card": card, "window": (max(0.0, start - 0.15 - (0.25 if i == 0 else 0)), end),
                      "words": words})
        print(f"   ayah {a['number'] or 'basmala'}: {len(a['words'])} words, timing={a['timing_source']}")

    reel = compose(background=bg, timeline=Timeline(cards, style, total), audio=audio, total=total,
                   dest=OUT / "reel.mp4", W=v["width"], H=v["height"], fps=v["fps"],
                   darken=v["background_darken"])

    caps = {}
    for platform, pcfg in cfg["platforms"].items():
        caps[platform] = captions.build_caption(plan, platform, pcfg["hashtags"])
        (OUT / f"caption_{platform}.txt").write_text(caps[platform], encoding="utf-8")
    caps["_yt_title"] = captions.youtube_title(plan)
    caps["_yt_tags"] = captions.youtube_tags(plan)

    plan_out = {**plan, "background": bg_id, "background_credit": credit, "duration": round(total, 2),
                "reciter": reciter["key"], "reciter_name": reciter["name"]}
    plan_out["ayahs"] = [{"number": a["number"], "text": a["text"], "tafsir": a["tafsir"],
                          "timing_source": a["timing_source"]} for a in plan["ayahs"]]
    save_json(OUT / "plan.json", plan_out)
    (OUT / "audio.wav").unlink()
    return reel, caps, plan_out


def publish(cfg, reel, caps, platforms):
    results = {}
    for name in platforms:
        print(f"🚀 Publishing to {name} …")
        try:
            if name == "facebook":
                from .publish_meta import publish_facebook
                results[name] = {"ok": True, **publish_facebook(cfg, reel, caps[name])}
            elif name == "instagram":
                from .publish_meta import publish_instagram
                results[name] = {"ok": True, **publish_instagram(cfg, reel, caps[name])}
            elif name == "youtube":
                from .publish_youtube import publish_youtube
                results[name] = {"ok": True, **publish_youtube(cfg, reel, caps[name], caps["_yt_title"],
                                                               caps["_yt_tags"])}
            elif name == "tiktok":
                from .publish_tiktok import publish_tiktok
                results[name] = {"ok": True, **publish_tiktok(cfg, reel, caps[name])}
            print(f"   ✅ {results[name]}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            results[name] = {"ok": False, "error": str(e)[:500]}
            print(f"   ❌ {name}: {e}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--platforms", default="")
    ap.add_argument("--passage")
    ap.add_argument("--reciter")
    args = ap.parse_args()

    cfg = load_json(ROOT / "config.json")
    history = load_history()
    reel, caps, plan = generate(cfg, args, history)
    print(f"🎬 Reel ready: {reel}  ({media_duration(reel):.1f}s)")

    if not args.publish:
        print("\n--- caption (instagram) ---\n" + caps["instagram"])
        return

    platforms = [p for p in (args.platforms.split(",") if args.platforms else cfg["platforms"])
                 if p and cfg["platforms"].get(p, {}).get("enabled")]
    results = publish(cfg, reel, caps, platforms)

    history["posts"].append({
        "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "passage_id": plan["passage_id"], "surah": plan["surah"],
        "ayahs": [a["number"] for a in plan["ayahs"] if a["number"]],
        "reciter": plan["reciter"], "background": plan["background"], "results": results,
    })
    save_json(HISTORY, history)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if results and not any(r["ok"] for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
