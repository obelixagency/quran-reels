"""Read-only report: reach of every Facebook / Instagram post we published (Arabic + English).

Uses the same page tokens as the publishing workflows, only GET requests. Prints a table and a JSON
file (insights.json) that is uploaded as an artifact of the run.
"""
import datetime as dt
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
G = "https://graph.facebook.com/v23.0"
CH = {
    "ar": dict(page=os.getenv("FB_PAGE_ID"), tok=os.getenv("FB_PAGE_TOKEN"), ig=os.getenv("IG_USER_ID"),
               igtok=os.getenv("IG_TOKEN") or os.getenv("FB_PAGE_TOKEN"),
               files=["history.json", "posts_history.json", "adhkar_history.json"]),
    "en": dict(page=os.getenv("EN_FB_PAGE_ID"), tok=os.getenv("EN_FB_PAGE_TOKEN"), ig=os.getenv("EN_IG_USER_ID"),
               igtok=os.getenv("EN_IG_TOKEN") or os.getenv("EN_FB_PAGE_TOKEN"),
               files=["history_en.json", "posts_history_en.json", "adhkar_history_en.json"]),
}


def get(path, tok, **params):
    try:
        r = requests.get(f"{G}/{path}", params={**params, "access_token": tok}, timeout=30)
        j = r.json()
        return (j, None) if r.ok else (None, f"HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def metrics(j):
    out = {}
    for m in (j or {}).get("data", []):
        v = m.get("values", [{}])
        val = v[0].get("value") if v else m.get("total_value", {}).get("value")
        if val is None and "total_value" in m:
            val = m["total_value"].get("value")
        out[m["name"]] = val
    return out


def fb_video(vid, tok):
    for ms in ("blue_reels_play_count,post_impressions_unique", "total_video_views,total_video_impressions_unique",
               "total_video_views"):
        j, err = get(f"{vid}/video_insights", tok, metric=ms)
        if j and j.get("data"):
            return metrics(j), None
    j, err = get(vid, tok, fields="views,created_time")
    return ({"views": j.get("views")} if j else {}), err


def fb_post(pid, tok):
    j, err = get(f"{pid}/insights", tok, metric="post_impressions_unique,post_clicks")
    if j and j.get("data"):
        return metrics(j), None
    j2, err2 = get(pid, tok, fields="reactions.summary(true),shares,comments.summary(true)")
    if j2:
        return {"reactions": j2.get("reactions", {}).get("summary", {}).get("total_count"),
                "shares": (j2.get("shares") or {}).get("count", 0)}, None
    return {}, err or err2


def ig_media(mid, tok):
    for ms in ("views,reach,likes,saved,shares,comments", "reach,likes,saved,shares", "impressions,reach"):
        j, err = get(f"{mid}/insights", tok, metric=ms)
        if j and j.get("data"):
            return metrics(j), None
    return {}, err


def main():
    rows, accounts = [], {}
    for ch, c in CH.items():
        if not c["tok"]:
            print(f"{ch}: no token – skipped")
            continue
        j, err = get(c["page"], c["tok"], fields="name,followers_count,fan_count")
        accounts[f"{ch}-facebook"] = ({k: j[k] for k in ("id", "name", "followers_count", "fan_count") if k in j} if j else err)
        if c["ig"]:
            j, err = get(c["ig"], c["igtok"], fields="username,followers_count,media_count")
            accounts[f"{ch}-instagram"] = ({k: j[k] for k in ("id", "username", "followers_count", "media_count") if k in j} if j else err)
        for fname in c["files"]:
            p = ROOT / fname
            if not p.exists():
                continue
            data = json.loads(p.read_text())
            items = data.get("posts") or data.get("sessions") or []
            for it in items:
                when = it.get("date", "")
                kind = it.get("kind") or it.get("type") or it.get("session") or fname.split("_")[0]
                res = it.get("results")
                if isinstance(res, list):  # adhkar sessions = stories only, no public numbers
                    continue
                for plat, r in (res or {}).items():
                    if not isinstance(r, dict) or not r.get("ok") or "story" in plat:
                        continue
                    if plat == "facebook":
                        if r.get("video_id"):
                            m, e = fb_video(r["video_id"], c["tok"])
                        elif r.get("post_id"):
                            m, e = fb_post(r["post_id"], c["tok"])
                        else:
                            continue
                    elif plat == "instagram" and r.get("media_id"):
                        m, e = ig_media(r["media_id"], c["igtok"])
                    else:
                        continue
                    rows.append({"ch": ch, "platform": plat, "file": fname, "kind": kind, "date": when,
                                 "metrics": m, "error": e})
    print(json.dumps(accounts, ensure_ascii=False, indent=1))
    for r in rows:
        t = dt.datetime.fromisoformat(r["date"]) + dt.timedelta(hours=3) if r["date"] else None
        print(f"{r['ch']} {r['platform']:9} {r['file']:22} {str(r['kind'])[:10]:10} "
              f"{t.strftime('%m-%d %H:%M') if t else '':11} {json.dumps(r['metrics'])} {r['error'] or ''}")
    (ROOT / "insights.json").write_text(json.dumps({"accounts": accounts, "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Operation failed; provider details withheld") from None

