"""النشر على قناة يوتيوب كـ Shorts عن طريق YouTube Data API v3 الرسمي – مجاني.

المتغيرات (GitHub Secrets):
  YT_CLIENT_ID, YT_CLIENT_SECRET   من Google Cloud Console (OAuth client – نوع Desktop app)
  YT_REFRESH_TOKEN                 من tools/setup_youtube.py (بتختار القناة وقت تسجيل الدخول)
  YT_CHANNEL_ID  (اختياري)         لو محطوط، النشر بيتلغي لو التوكن تبع قناة تانية

ملاحظات:
- الفيديو الرأسي اللي أقل من ٣ دقايق يوتيوب بيعرضه كـ Short تلقائيًا، وبنضيف #Shorts للعنوان.
- مشروع Google Cloud الجديد (غير متحقق منه) الفيديوهات اللي بيرفعها بتتقفل "خاص" لحد ما
  تعمل Audit مجاني من يوتيوب. بعد الموافقة بتتنشر عامة عادي.
- الحصة المجانية: ١٠٬٠٠٠ وحدة يوميًا، والرفع الواحد = ١٦٠٠ وحدة → لحد ٦ فيديوهات في اليوم.
"""
import os
from pathlib import Path

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"


def access_token():
    r = requests.post(TOKEN_URL, timeout=60, data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"YouTube token refresh failed: {data}")
    return data["access_token"]


def _check_channel(h):
    r = requests.get(f"{API}/channels", params={"part": "id,snippet", "mine": "true"}, headers=h, timeout=60)
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError(f"No YouTube channel for this token: {r.text[:300]}")
    ch = items[0]
    wanted = os.getenv("YT_CHANNEL_ID")
    if wanted and ch["id"] != wanted:
        raise RuntimeError(f"Token belongs to channel {ch['id']} ({ch['snippet']['title']}), not {wanted}")
    return ch


def publish_youtube(cfg, video_path, caption, title, tags, cover=None):
    ycfg = cfg["platforms"]["youtube"]
    h = {"Authorization": f"Bearer {access_token()}"}
    ch = _check_channel(h)
    size = Path(video_path).stat().st_size

    body = {
        "snippet": {"title": title[:100], "description": caption[:4900], "tags": tags[:15],
                    "categoryId": str(ycfg.get("category_id", "22")), "defaultLanguage": ycfg.get("language", "ar"),
                    "defaultAudioLanguage": ycfg.get("language", "ar")},
        "status": {"privacyStatus": ycfg.get("privacy", "public"), "selfDeclaredMadeForKids": False,
                   "embeddable": True},
    }
    init = requests.post(UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"}, json=body,
                         timeout=60, headers={**h, "X-Upload-Content-Type": "video/mp4",
                                              "X-Upload-Content-Length": str(size)})
    if init.status_code >= 400 or "Location" not in init.headers:
        raise RuntimeError(f"YouTube upload init failed {init.status_code}: {init.text[:500]}")

    with open(video_path, "rb") as f:
        up = requests.put(init.headers["Location"], data=f, timeout=900,
                          headers={**h, "Content-Type": "video/mp4", "Content-Length": str(size)})
    if up.status_code >= 400:
        raise RuntimeError(f"YouTube upload failed {up.status_code}: {up.text[:500]}")
    vid = up.json()
    thumb = None
    if cover and Path(cover["path"]).exists():
        # يوتيوب بيسمح بالكوفر المخصص بس للقنوات المتوثقة برقم تليفون – لو رفض، الفيديو نفسه اتنشر عادي
        with open(cover["path"], "rb") as img:
            t = requests.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                              params={"videoId": vid["id"]}, data=img, timeout=120,
                              headers={**h, "Content-Type": "image/jpeg"})
        thumb = "ok" if t.status_code < 300 else f"skipped ({t.status_code}): {t.text[:150]}"
    return {"cover": thumb, "video_id": vid["id"], "url": f"https://youtube.com/shorts/{vid['id']}",
            "privacy": vid.get("status", {}).get("privacyStatus"), "channel": ch["snippet"]["title"]}
