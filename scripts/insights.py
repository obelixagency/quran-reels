"""Insights for every post we published (Arabic + English): Facebook, Instagram, YouTube. Read-only.

* Every published item is scored per platform (stats.json, key "<platform>:<id>") and re-read on every run
  while it is younger than 60 days, so platforms that were missed before are filled in retroactively.
  A "d4" snapshot is kept the first time an item is 3.5–7 days old (that is what slot comparisons use).
* Each entry carries slot_local: the publish time in the audience's time zone (Cairo for Arabic,
  New York for English), computed with zoneinfo so summer/winter time is handled.
* insights_report.md is rewritten on every run: per channel / platform / slot → count, median, total.
* A read-only capability check (publishing rights, page/IG/reel insights, comments) goes into the
  report and the run summary. Nothing is posted.
Errors are never swallowed silently: they are stored on the entry ("error") and listed in the report.
"""
import datetime as dt
import json
import os
import statistics
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "stats.json"
REPORT = ROOT / "insights_report.md"
G = "https://graph.facebook.com/v23.0"
MAX_AGE_DAYS = 60
NOW = dt.datetime.now(dt.timezone.utc)
CH = {
    "ar": dict(page="FB_PAGE_ID", tok="FB_PAGE_TOKEN", ig="IG_USER_ID", igtok="IG_TOKEN", tz="Africa/Cairo",
               files=["history.json", "posts_history.json", "shorts_history.json"],
               yt=("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")),
    "en": dict(page="EN_FB_PAGE_ID", tok="EN_FB_PAGE_TOKEN", ig="EN_IG_USER_ID", igtok="EN_IG_TOKEN",
               tz="America/New_York", files=["history_en.json", "posts_history_en.json"],
               yt=("EN_YT_CLIENT_ID", "EN_YT_CLIENT_SECRET", "EN_YT_REFRESH_TOKEN")),
}
MAIN = {"facebook": ["blue_reels_play_count", "post_total_media_view_unique", "views"],
        "instagram": ["views", "reach"], "youtube": ["views"]}


def get(path, tok, **params):
    try:
        r = requests.get(f"{G}/{path}", params={**params, "access_token": tok}, timeout=30)
        j = r.json()
        if r.ok:
            return j, None
        e = j.get("error", {})
        return None, f"HTTP {r.status_code} code {e.get('code')}: {str(e.get('message', ''))[:90]}"
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def metrics(j):
    out = {}
    for m in (j or {}).get("data", []):
        vals = m.get("values") or []
        val = vals[0].get("value") if vals else (m.get("total_value") or {}).get("value")
        out[m["name"]] = val
    return out


def fb_video(vid, tok):
    j, err = get(f"{vid}/video_insights", tok, metric="blue_reels_play_count,post_video_avg_time_watched")
    if j and j.get("data"):
        return metrics(j), None
    j2, err2 = get(f"{vid}/video_insights", tok, metric="total_video_views")
    if j2 and j2.get("data"):
        return {"views": metrics(j2).get("total_video_views")}, None
    return {}, err or err2


def fb_post(pid, tok):
    j, err = get(f"{pid}/insights", tok, metric="post_total_media_view_unique,post_clicks")
    if j and j.get("data"):
        return metrics(j), None
    return {}, err


def ig_media(mid, tok):
    for ms in ("views,reach,likes,saved,shares,comments", "reach,likes,saved,shares,comments"):
        j, err = get(f"{mid}/insights", tok, metric=ms)
        if j and j.get("data"):
            return metrics(j), None
    return {}, err


def yt_token(names):
    cid, sec, rt = (os.getenv(n) for n in names)
    if not (cid and sec and rt):
        return None, "YouTube secrets missing"
    try:
        j = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
            "client_id": cid, "client_secret": sec, "refresh_token": rt, "grant_type": "refresh_token"}).json()
        return j.get("access_token"), (None if j.get("access_token") else f"token refresh: {j.get('error')}")
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def yt_stats(ids, at):
    out, err = {}, None
    ids = list(dict.fromkeys(i for i in ids if i))
    for k in range(0, len(ids), 50):
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30,
                             headers={"Authorization": f"Bearer {at}"},
                             params={"part": "statistics", "id": ",".join(ids[k:k + 50])})
            if not r.ok:
                err = f"HTTP {r.status_code}"
                continue
            for it in r.json().get("items", []):
                st = it.get("statistics", {})
                out[it["id"]] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                                 "comments": int(st.get("commentCount", 0))}
        except Exception as e:  # noqa: BLE001
            err = type(e).__name__
    return out, err


def parse_date(s):
    try:
        d = dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def main_value(platform, m):
    for k in MAIN[platform]:
        if isinstance((m or {}).get(k), (int, float)):
            return m[k]
    return None


def collect(ch, c, long_hist):
    """[(platform, file, kind, date, id, type)] for every successfully published item."""
    items = []
    for fname in c["files"]:
        p = ROOT / fname
        if not p.exists():
            continue
        for it in json.loads(p.read_text()).get("posts", []):
            kind = it.get("kind") or it.get("type") or fname.split("_")[0]
            for plat, r in (it.get("results") or {}).items():
                if not isinstance(r, dict) or not r.get("ok") or "story" in plat:
                    continue
                if plat == "youtube" and r.get("video_id"):
                    items.append(("youtube", fname, kind, it.get("date", ""), r["video_id"], "video"))
                elif plat == "facebook" and r.get("video_id"):
                    items.append(("facebook", fname, kind, it.get("date", ""), r["video_id"], "video"))
                elif plat == "facebook" and r.get("post_id"):
                    items.append(("facebook", fname, kind, it.get("date", ""), r["post_id"], "post"))
                elif plat == "instagram" and r.get("media_id"):
                    items.append(("instagram", fname, kind, it.get("date", ""), r["media_id"], "media"))
    for v in long_hist.get("videos", []):
        if v.get("channel") == ch and v.get("video_id"):
            items.append(("youtube", "long_history.json", f"long-{v.get('kind')}", v.get("date", ""), v["video_id"],
                          "video"))
    return items


def checks(ch, c):
    """Read-only capability check. Returns [(name, ok, detail)]."""
    tok, page, ig = os.getenv(c["tok"]), os.getenv(c["page"]), os.getenv(c["ig"])
    igtok = os.getenv(c["igtok"]) or tok
    out = []
    if not tok:
        return [("page token", False, "secret missing")]
    j, e = get(page, tok, fields="name,followers_count,fan_count")
    out.append(("page info", bool(j), j and f"{j.get('name')} – {j.get('followers_count')} followers" or e))
    j, e = get(f"{page}/published_posts", tok, limit=1)
    out.append(("page posts (pages_read_engagement)", bool(j), e or "ok"))
    j, e = get(f"{page}/insights", tok, metric="page_total_media_view_unique", period="day")
    out.append(("page insights (read_insights)", bool(j), e or f"last day: {metrics(j).get('page_total_media_view_unique')}"))
    j, e = get(f"{page}/videos", tok, limit=1, fields="id")
    vid = ((j or {}).get("data") or [{}])[0].get("id")
    if vid:
        m, e2 = fb_video(vid, tok)
        out.append(("reel insights", bool(m), e2 or json.dumps(m)))
        j, e3 = get(f"{vid}/comments", tok, limit=1)
        out.append(("Facebook comments read", bool(j), e3 or "ok"))
    if ig:
        j, e = get(ig, igtok, fields="username,followers_count,media_count")
        out.append(("Instagram account", bool(j), j and f"@{j.get('username')} – {j.get('followers_count')} followers" or e))
        j, e = get(f"{ig}/content_publishing_limit", igtok, fields="quota_usage,config")
        out.append(("Instagram publishing (instagram_content_publish)", bool(j), e or json.dumps((j.get('data') or [{}])[0])))
        j, e = get(f"{ig}/insights", igtok, metric="reach", period="day")
        out.append(("Instagram account insights (instagram_manage_insights)", bool(j), e or "ok"))
        j, e = get(f"{ig}/media", igtok, limit=1, fields="id")
        mid = ((j or {}).get("data") or [{}])[0].get("id")
        if mid:
            j, e = get(f"{mid}/comments", igtok, limit=1)
            out.append(("Instagram comments read (instagram_manage_comments)", bool(j), e or "ok"))
    return out


def slot_of(local):
    """Round to the nearest half hour: posts land 10–50 min after the cron time."""
    m = local.hour * 60 + local.minute
    m = int(m / 30.0 + 0.5) * 30 % 1440  # 19:15 → 19:30 (no banker's rounding)
    return f"{m // 60:02d}:{m % 60:02d}"


def report(stats, check_res, problems):
    lines = [f"# Insights report – updated {NOW:%Y-%m-%d %H:%M} UTC", "",
             "Median/total are views (Facebook reels: plays · Facebook posts: unique media views · Instagram: views "
             "· YouTube: views), measured ~4 days after publishing where available. Slot = local time of the "
             "audience (Cairo for Arabic, New York for English).", ""]
    for ch in ("ar", "en"):
        lines += [f"## {'سَكينة يومية (عربي) – Cairo' if ch == 'ar' else 'Daily Serenity (English) – New York'}", ""]
        for name, ok, detail in check_res.get(ch, []):
            lines.append(f"- {'✅' if ok else '❌'} {name}: {detail}")
        lines.append("")
        for plat in ("facebook", "instagram", "youtube"):
            groups = {}
            for s in stats.values():
                if s["ch"] != ch or s["platform"] != plat:
                    continue
                v = s.get("d4_value") if s.get("d4_value") is not None else (
                    s.get("value") if (s.get("age_days") or 0) >= 4 else None)
                if v is None:
                    continue
                groups.setdefault((s["group"], s["slot_local"]), []).append(v)
            if not groups:
                continue
            lines += [f"### {plat}", "", "| type | slot | videos | median | total |", "|---|---|---:|---:|---:|"]
            for (g, slot), vals in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
                lines.append(f"| {g} | {slot} | {len(vals)} | {statistics.median(vals):,.0f} | {sum(vals):,.0f} |")
            lines.append("")
    if problems:
        lines += ["## Errors (not hidden)", ""] + [f"- {p}" for p in problems[:80]] + [""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    stats = json.loads(STATS.read_text()) if STATS.exists() else {}
    try:
        long_hist = requests.get("https://raw.githubusercontent.com/obelixagency/quran-long-videos/main/long_history.json",
                                 timeout=30).json()
    except Exception as e:  # noqa: BLE001
        long_hist, _ = {}, print(f"long_history.json: {type(e).__name__}")
    check_res, problems = {}, []
    for ch, c in CH.items():
        check_res[ch] = checks(ch, c)
        tok = os.getenv(c["tok"])
        igtok = os.getenv(c["igtok"]) or tok
        tz = ZoneInfo(c["tz"])
        items = collect(ch, c, long_hist)
        at, yerr = yt_token(c["yt"])
        yt_ids = [i[4] for i in items if i[0] == "youtube"]
        ytm, yerr2 = yt_stats(yt_ids, at) if at else ({}, yerr)
        if yerr or yerr2:
            problems.append(f"{ch} youtube: {yerr or yerr2}")
        for plat, fname, kind, date, oid, typ in items:
            d = parse_date(date)
            if not d:
                continue
            age = (NOW - d).total_seconds() / 86400
            key = f"{plat}:{oid}"
            s = stats.get(key) or {}
            local = d.astimezone(tz)
            group = ("long" if fname == "long_history.json" else "post" if fname.startswith("posts")
                     else "short" if fname.startswith("shorts") else "reel")
            s.update({"ch": ch, "platform": plat, "file": fname, "kind": kind, "group": group,
                      "date_utc": d.isoformat(), "slot_local": slot_of(local), "local": local.isoformat(),
                      "age_days": round(age, 1)})
            if age > MAX_AGE_DAYS and "value" in s:
                stats[key] = s
                continue
            if age < 0.5:
                stats[key] = s
                continue
            if plat == "youtube":
                m, e = (ytm.get(oid), None) if oid in ytm else ({}, yerr or yerr2 or "not found")
            elif not tok:
                m, e = {}, "no Meta token"
            elif plat == "facebook":
                m, e = fb_video(oid, tok) if typ == "video" else fb_post(oid, tok)
            else:
                m, e = ig_media(oid, igtok)
            s["scored_on"] = NOW.isoformat(timespec="seconds")
            if m:
                s["metrics"], s["value"] = m, main_value(plat, m)
                s.pop("error", None)
                if 3.5 <= age <= 7 and "d4_value" not in s:
                    s["d4_value"], s["d4_metrics"] = s["value"], m
            else:
                s["error"] = e
                if plat != "youtube" or e != "not found":
                    problems.append(f"{ch} {plat} {kind} {local:%m-%d %H:%M}: {e}")
            stats[key] = s
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    report(stats, check_res, problems)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    text = REPORT.read_text(encoding="utf-8")
    print(text)
    if summary:
        Path(summary).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Insights failed; provider details withheld") from None
