"""Shares each new long YouTube video on the matching Facebook page (a link post with the video preview).

Runs at the end of every watchdog run. Reads the public long_history.json of quran-long-videos and
remembers what it already shared in promoted_long.json. Per channel it shares only the newest video
that is less than 12 h old, so a late run never floods the page.
"""
import datetime as dt
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "promoted_long.json"
SRC = "https://raw.githubusercontent.com/obelixagency/quran-long-videos/main/long_history.json"
GRAPH = "https://graph.facebook.com/v23.0"
PAGES = {"ar": ("FB_PAGE_ID", "FB_PAGE_TOKEN"), "en": ("EN_FB_PAGE_ID", "EN_FB_PAGE_TOKEN")}
TEXT = {
    "ar": "🎧 فيديو جديد على قناتنا في يوتيوب\n\n{title}\n\nاسمعه كامل من هنا 👇\n{url}\n\n"
          "اشترك في القناة عشان يوصلك كل يوم تلاوة جديدة 🤍",
    "en": "🎧 New on our YouTube channel\n\n{title}\n\nListen to the full recitation here 👇\n{url}\n\n"
          "Subscribe for a calm Quran recitation every day 🤍",
}
MAX_AGE = dt.timedelta(hours=12)


def main():
    hist = requests.get(SRC, timeout=30).json()["videos"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {"shared": []}
    done = set(state["shared"])
    now = dt.datetime.now(dt.timezone.utc)
    changed = False
    for ch, (pid_key, tok_key) in PAGES.items():
        new = [v for v in hist if v.get("channel") == ch and v.get("video_id") and v["video_id"] not in done]
        if not new:
            continue
        new.sort(key=lambda v: v.get("date", ""))
        newest = new[-1]
        for v in new[:-1]:  # older ones are only marked, never posted late
            done.add(v["video_id"])
            changed = True
        age = now - dt.datetime.fromisoformat(newest["date"])
        title = newest.get("title") or ""
        if age > MAX_AGE or title.startswith("("):
            done.add(newest["video_id"])
            changed = True
            continue
        pid, tok = os.getenv(pid_key), os.getenv(tok_key)
        if not pid or not tok:
            print(f"{ch}: Facebook secrets missing – skipped")
            continue
        url = f"https://youtu.be/{newest['video_id']}"
        r = requests.post(f"{GRAPH}/{pid}/feed", timeout=60, data={
            "message": TEXT[ch].format(title=title, url=url), "link": url, "access_token": tok})
        print(f"{ch}: shared {url} on Facebook -> {r.status_code} {r.text[:200]}")
        if r.ok:
            done.add(newest["video_id"])
            changed = True
    if changed:
        state["shared"] = sorted(done)
        STATE.write_text(json.dumps(state, indent=2) + "\n")
    print("state updated" if changed else "nothing new to share")


if __name__ == "__main__":
    main()
