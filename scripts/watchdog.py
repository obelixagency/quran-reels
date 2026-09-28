"""Watchdog: makes sure every scheduled post actually went out.

Runs every 30 minutes. For each publishing workflow it reads the main cron times (the lines
without "# backup"), and for every time slot that started 75 min – 6 h ago it checks the
workflow's runs since that slot:
  * a successful or still running/queued run  -> fine
  * nothing at all (GitHub skipped every cron) -> starts the workflow itself (workflow_dispatch)
  * the watchdog already started one and it failed -> opens a GitHub issue so you get notified
Everything it does is written to the run summary.
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

REPO = os.environ["GITHUB_REPOSITORY"]
API = f"https://api.github.com/repos/{REPO}"
H = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}
ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime.now(dt.timezone.utc)
SUMMARY = []


def log(msg):
    print(msg)
    SUMMARY.append(msg)


def en_enabled():
    try:
        return bool(json.loads((ROOT / "config.json").read_text())["en"]["enabled"])
    except Exception:  # noqa: BLE001
        return False


# workflow file -> function(hour_utc) -> (dispatch inputs, label)
WORKFLOWS = {
    "daily-adhkar.yml": lambda h: ({"session": "morning" if h < 9 else "evening", "publish": "true"},
                                   "أذكار " + ("الصباح" if h < 9 else "المساء") + " (عربي)"),
    "daily-post.yml": lambda h: ({"publish": "true"}, "بوست دعاء/حديث (عربي)"),
    "daily-reel.yml": lambda h: ({"publish": "true"}, "ريل التلاوة (عربي)"),
    "serenity-adhkar.yml": lambda h: ({"session": "morning" if h < 16 else "evening", "publish": "true"},
                                      "Adhkar " + ("morning" if h < 16 else "evening") + " (EN)"),
    "serenity-reels.yml": lambda h: ({"kind": "recited" if 12 <= h <= 14 else "quran" if 15 <= h <= 20 else "sunnah",
                                      "publish": "true"},
                                     ("Recited Quran reel" if 12 <= h <= 14 else "Quran reel" if 15 <= h <= 20
                                      else "Hadith/dua reel") + " (EN)"),
}


def main_crons(wf):
    text = (ROOT / ".github" / "workflows" / wf).read_text()
    out = []
    for line in text.splitlines():
        m = re.match(r'\s*- cron: "(\d+) (\d+) \* \* \*"(.*)$', line)
        if m and "backup" not in m.group(3):
            out.append((int(m.group(2)), int(m.group(1))))
    return out


def last_slot(hour, minute):
    s = NOW.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return s if s <= NOW else s - dt.timedelta(days=1)


def runs_since(wf, since):
    r = requests.get(f"{API}/actions/workflows/{wf}/runs", headers=H, timeout=30,
                     params={"created": ">=" + since.strftime("%Y-%m-%dT%H:%M:%SZ"), "per_page": 50})
    r.raise_for_status()
    return r.json()["workflow_runs"]


def open_issue(title, body):
    r = requests.get(f"{API}/issues", headers=H, timeout=30, params={"state": "open", "labels": "watchdog"})
    if any(i["title"] == title for i in r.json()):
        return
    requests.post(f"{API}/labels", headers=H, timeout=30, json={"name": "watchdog", "color": "d93f0b"})
    requests.post(f"{API}/issues", headers=H, timeout=30,
                  json={"title": title, "body": body, "labels": ["watchdog"]}).raise_for_status()


def check(wf, hour, minute):
    inputs, label = WORKFLOWS[wf](hour)
    slot = last_slot(hour, minute)
    age = (NOW - slot).total_seconds() / 60
    if not 75 <= age <= 360:
        return
    runs = runs_since(wf, slot - dt.timedelta(minutes=15))
    ok = [r for r in runs if r["conclusion"] == "success" or r["status"] in ("queued", "in_progress", "waiting", "pending", "requested")]
    if ok:
        log(f"✅ {label} {slot:%H:%M} UTC – ok ({ok[0]['event']})")
        return
    mine = [r for r in runs if r["event"] == "workflow_dispatch" and (r.get("triggering_actor") or {}).get("login") == "github-actions[bot]"]
    if mine:
        log(f"❌ {label} {slot:%H:%M} UTC – retry by the watchdog failed: {mine[0]['html_url']}")
        open_issue(f"⚠️ لم يُنشر: {label} – {slot:%Y-%m-%d}",
                   f"الميعاد {slot:%H:%M} UTC ما اتنشرش، والمحاولة التلقائية فشلت.\n\n{mine[0]['html_url']}")
        return
    r = requests.post(f"{API}/actions/workflows/{wf}/dispatches", headers=H, timeout=30,
                      json={"ref": "main", "inputs": inputs})
    if r.status_code == 204:
        log(f"🔁 {label} {slot:%H:%M} UTC – GitHub skipped it, started it now")
    else:
        log(f"❌ {label} – could not start it ({r.status_code}): {r.text[:200]}")
        open_issue(f"⚠️ لم يُنشر: {label} – {slot:%Y-%m-%d}", f"الـ watchdog ما قدرش يشغّله: {r.status_code} {r.text[:300]}")


def main():
    en = en_enabled()
    for wf in WORKFLOWS:
        if wf.startswith("serenity") and not en:
            continue
        for hour, minute in main_crons(wf):
            try:
                check(wf, hour, minute)
            except Exception as e:  # noqa: BLE001
                log(f"⚠️ {wf} {hour:02d}:{minute:02d} – {e}")
    if not SUMMARY:
        SUMMARY.append("No time slot to check right now.")
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        Path(p).write_text("## Watchdog\n\n" + "\n\n".join(SUMMARY) + "\n")


if __name__ == "__main__":
    sys.exit(main())
