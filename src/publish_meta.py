"""النشر على صفحة فيسبوك (Reels) وحساب إنستجرام (Reels) عن طريق Meta Graph API الرسمي – مجاني.

المتغيرات المطلوبة (GitHub Secrets):
  FB_PAGE_ID            رقم صفحة الفيسبوك
  FB_PAGE_TOKEN         Page Access Token (مش بينتهي لو اتعمل بالطريقة اللي في tools/setup_meta.py)
  IG_USER_ID            رقم حساب إنستجرام البيزنس المربوط بالصفحة
"""
import os
import time
from pathlib import Path

import requests


def _graph(cfg):
    return f"https://graph.facebook.com/{cfg.get('graph_api_version', 'v23.0')}"


def _check(r):
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text}
    if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        raise RuntimeError(f"Meta API error {r.status_code}: {data}")
    return data


def publish_facebook(cfg, video_path, caption):
    page_id, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    size = Path(video_path).stat().st_size

    start = _check(requests.post(f"{g}/{page_id}/video_reels",
                                 data={"upload_phase": "start", "access_token": token}, timeout=60))
    video_id, upload_url = start["video_id"], start["upload_url"]

    with open(video_path, "rb") as f:
        _check(requests.post(upload_url, data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}))

    _check(requests.post(f"{g}/{page_id}/video_reels", timeout=60, data={
        "access_token": token, "video_id": video_id, "upload_phase": "finish",
        "video_state": "PUBLISHED", "description": caption}))

    # wait until processed/published (max ~5 min)
    status = {}
    for _ in range(30):
        time.sleep(10)
        status = _check(requests.get(f"{g}/{video_id}", params={"fields": "status", "access_token": token},
                                     timeout=60)).get("status", {})
        if status.get("video_status") in ("ready", "published") or \
                status.get("publishing_phase", {}).get("status") == "complete":
            break
        if status.get("video_status") == "error":
            raise RuntimeError(f"Facebook processing error: {status}")
    return {"video_id": video_id, "status": status.get("video_status")}


def publish_instagram(cfg, video_path, caption):
    ig_id, token = os.environ["IG_USER_ID"], os.environ.get("IG_TOKEN") or os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    version = cfg.get("graph_api_version", "v23.0")
    size = Path(video_path).stat().st_size

    container = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": "true", "access_token": token}))
    cid = container["id"]

    with open(video_path, "rb") as f:
        _check(requests.post(f"https://rupload.facebook.com/ig-api-upload/{version}/{cid}", data=f,
                             timeout=600, headers={"Authorization": f"OAuth {token}",
                                                   "offset": "0", "file_size": str(size)}))

    for _ in range(40):
        time.sleep(10)
        st = _check(requests.get(f"{g}/{cid}", params={"fields": "status_code,status", "access_token": token},
                                 timeout=60))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing error: {st}")
    else:
        raise RuntimeError("Instagram processing timed out")

    pub = _check(requests.post(f"{g}/{ig_id}/media_publish", timeout=60,
                               data={"creation_id": cid, "access_token": token}))
    return {"media_id": pub.get("id")}
