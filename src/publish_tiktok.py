"""النشر على تيك توك عن طريق TikTok Content Posting API الرسمي – مجاني.

وضعين (config.json → platforms.tiktok.mode):
  "draft"  : الفيديو بيوصل لصندوق الوارد/المسودات في تطبيق تيك توك، وانت تدوس "نشر" (وتلزق الكابشن
             الموجود في caption_tiktok.txt). ده الوضع اللي بيشتغل من أول يوم.
  "direct" : نشر مباشر بالكابشن. قبل ما TikTok يعمل Audit للتطبيق، الفيديو بيتنشر "خاص" (SELF_ONLY) بس.
             بعد الموافقة غيّر privacy_level لـ PUBLIC_TO_EVERYONE.

المتغيرات: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
"""
import os
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"


def _check(r):
    data = r.json()
    err = data.get("error", {})
    if r.status_code >= 400 or (err and err.get("code") not in (None, "ok")):
        raise RuntimeError(f"TikTok API error {r.status_code}: {data}")
    return data


def access_token():
    r = requests.post(f"{API}/oauth/token/", timeout=60, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    new_rt = data.get("refresh_token")
    if new_rt and new_rt != os.environ["TIKTOK_REFRESH_TOKEN"]:
        # the workflow picks this file up and updates the GitHub secret (if GH_PAT is configured)
        Path("out/.tiktok_refresh_token").write_text(new_rt)
    return data["access_token"]


def publish_tiktok(cfg, video_path, caption):
    tcfg = cfg["platforms"]["tiktok"]
    token = access_token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    size = Path(video_path).stat().st_size
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}

    if tcfg.get("mode", "draft") == "direct":
        info = _check(requests.post(f"{API}/post/publish/creator_info/query/", headers=h, timeout=60))["data"]
        wanted = tcfg.get("privacy_level", "PUBLIC_TO_EVERYONE")
        options = info.get("privacy_level_options", [])
        privacy = wanted if wanted in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])
        body = {"post_info": {"title": caption[:2200], "privacy_level": privacy,
                              "disable_comment": False, "disable_duet": False, "disable_stitch": False},
                "source_info": source}
        init = _check(requests.post(f"{API}/post/publish/video/init/", headers=h, json=body, timeout=60))["data"]
    else:
        init = _check(requests.post(f"{API}/post/publish/inbox/video/init/", headers=h,
                                    json={"source_info": source}, timeout=60))["data"]

    with open(video_path, "rb") as f:
        r = requests.put(init["upload_url"], data=f, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}"})
        if r.status_code >= 400:
            raise RuntimeError(f"TikTok upload failed {r.status_code}: {r.text[:500]}")

    status = None
    for _ in range(30):
        time.sleep(10)
        st = _check(requests.post(f"{API}/post/publish/status/fetch/", headers=h, timeout=60,
                                  json={"publish_id": init["publish_id"]}))["data"]
        status = st.get("status")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok publish failed: {st}")
    return {"publish_id": init["publish_id"], "status": status, "mode": tcfg.get("mode", "draft")}
