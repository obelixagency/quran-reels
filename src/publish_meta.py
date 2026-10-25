"""النشر على صفحة فيسبوك (Reels) وحساب إنستجرام (Reels) عن طريق Meta Graph API الرسمي – مجاني.

المتغيرات المطلوبة (GitHub Secrets):
  FB_PAGE_ID            رقم صفحة الفيسبوك
  FB_PAGE_TOKEN         Page Access Token (مش بينتهي لو اتعمل بالطريقة اللي في tools/setup_meta.py)
  IG_USER_ID            رقم حساب إنستجرام البيزنس المربوط بالصفحة
"""
import json
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
        raise RuntimeError("Meta API returned invalid JSON") from None
    if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        raise RuntimeError(f"Meta API error {r.status_code}")
    return data


def publish_facebook(cfg, video_path, caption, cover=None):
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
            raise RuntimeError(f"Facebook processing error")
    thumb = None
    if cover and Path(cover["path"]).exists():  # الكوفر: آخر مشهد الآية كاملة
        try:
            with open(cover["path"], "rb") as img:
                thumb = requests.post(f"{g}/{video_id}/thumbnails", timeout=120,
                                      data={"access_token": token, "is_preferred": "true"},
                                      files={"source": ("cover.jpg", img, "image/jpeg")}).json()
        except Exception as e:  # noqa: BLE001
            thumb = {"error": type(e).__name__}
    return {"video_id": video_id, "status": status.get("video_status"),
            "cover": "ok" if thumb and not thumb.get("error") else "unavailable"}


def publish_instagram(cfg, video_path, caption, cover=None):
    ig_id, token = os.environ["IG_USER_ID"], os.environ.get("IG_TOKEN") or os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    version = cfg.get("graph_api_version", "v23.0")
    size = Path(video_path).stat().st_size

    data = {"media_type": "REELS", "upload_type": "resumable", "caption": caption,
            "share_to_feed": "true", "access_token": token}
    if cover:
        data["thumb_offset"] = str(cover["ms"])  # الكوفر = الفريم ده من الريل
    container = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data=data))
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
            raise RuntimeError(f"Instagram processing error")
    else:
        raise RuntimeError("Instagram processing timed out")

    pub = _check(requests.post(f"{g}/{ig_id}/media_publish", timeout=60,
                               data={"creation_id": cid, "access_token": token}))
    return {"media_id": pub.get("id")}


# ------------------------------------------------------------------ image posts (1080×1440)
def _photo_url(g, photo_id, token):
    info = _check(requests.get(f"{g}/{photo_id}", params={"fields": "images", "access_token": token}, timeout=60))
    imgs = sorted(info.get("images", []), key=lambda i: i.get("width", 0), reverse=True)
    return imgs[0]["source"] if imgs else None


def publish_facebook_photo(cfg, image_path, caption, published=True):
    page_id, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    with open(image_path, "rb") as img:
        r = _check(requests.post(f"{g}/{page_id}/photos", timeout=120,
                                 data={"access_token": token, "message": caption,
                                       "published": "true" if published else "false"},
                                 files={"source": ("post.jpg", img, "image/jpeg")}))
    return {"photo_id": r["id"], "post_id": r.get("post_id"), "image_url": _photo_url(g, r["id"], token)}


def publish_instagram_image(cfg, image_path, caption, image_url=None):
    """إنستجرام محتاج رابط عام للصورة → بنستخدم رابط الصورة اللي اترفعت على فيسبوك
    (ولو فيسبوك متقفل بنرفعها على الصفحة كصورة غير منشورة عشان ناخد الرابط)."""
    ig_id, token = os.environ["IG_USER_ID"], os.environ.get("IG_TOKEN") or os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    if not image_url:
        image_url = publish_facebook_photo(cfg, image_path, "", published=False)["image_url"]
    cid = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data={
        "image_url": image_url, "caption": caption, "access_token": token}))["id"]
    for _ in range(20):
        st = _check(requests.get(f"{g}/{cid}", params={"fields": "status_code", "access_token": token},
                                 timeout=60))
        if st.get("status_code") in (None, "FINISHED"):
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram image error")
        time.sleep(5)
    pub = _check(requests.post(f"{g}/{ig_id}/media_publish", timeout=60,
                               data={"creation_id": cid, "access_token": token}))
    return {"media_id": pub.get("id")}


# ------------------------------------------------------------------ carousel (عدة صور في منشور واحد)
def publish_facebook_carousel(cfg, image_paths, caption):
    """فيسبوك: بنرفع الصور غير منشورة وبعدين منشور واحد فيه كلهم (attached_media)."""
    page_id, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    photos = [publish_facebook_photo(cfg, pth, "", published=False) for pth in image_paths]
    data = {"message": caption, "access_token": token}
    for i, ph in enumerate(photos):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": ph["photo_id"]})
    r = _check(requests.post(f"{g}/{page_id}/feed", data=data, timeout=120))
    return {"post_id": r.get("id"), "image_urls": [ph["image_url"] for ph in photos]}


def publish_instagram_carousel(cfg, image_paths, caption, image_urls=None):
    ig_id, token = os.environ["IG_USER_ID"], os.environ.get("IG_TOKEN") or os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    if not image_urls or not all(image_urls):
        image_urls = [publish_facebook_photo(cfg, pth, "", published=False)["image_url"] for pth in image_paths]
    children = []
    for url in image_urls[:10]:
        cid = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data={
            "image_url": url, "is_carousel_item": "true", "access_token": token}))["id"]
        _wait_ig(g, cid, token, tries=15)
        children.append(cid)
    parent = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data={
        "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption,
        "access_token": token}))["id"]
    _wait_ig(g, parent, token, tries=20)
    pub = _check(requests.post(f"{g}/{ig_id}/media_publish", timeout=60,
                               data={"creation_id": parent, "access_token": token}))
    return {"media_id": pub.get("id"), "slides": len(children)}


# ------------------------------------------------------------------ stories
def _wait_ig(g, cid, token, tries=40):
    for _ in range(tries):
        st = _check(requests.get(f"{g}/{cid}", params={"fields": "status_code", "access_token": token},
                                 timeout=60))
        if st.get("status_code") in (None, "FINISHED"):
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram story error")
        time.sleep(8)
    raise RuntimeError("Instagram story processing timed out")


def story_facebook_video(cfg, video_path):
    page_id, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    size = Path(video_path).stat().st_size
    start = _check(requests.post(f"{g}/{page_id}/video_stories", timeout=60,
                                 data={"upload_phase": "start", "access_token": token}))
    with open(video_path, "rb") as f:
        _check(requests.post(start["upload_url"], data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}))
    time.sleep(5)
    done = _check(requests.post(f"{g}/{page_id}/video_stories", timeout=120, data={
        "upload_phase": "finish", "video_id": start["video_id"], "access_token": token}))
    return {"story_id": done.get("post_id") or start["video_id"]}


def story_facebook_photo(cfg, image_path):
    page_id, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    photo = publish_facebook_photo(cfg, image_path, "", published=False)
    done = _check(requests.post(f"{g}/{page_id}/photo_stories", timeout=60,
                                data={"photo_id": photo["photo_id"], "access_token": token}))
    return {"story_id": done.get("post_id"), "image_url": photo["image_url"]}


def story_instagram_video(cfg, video_path):
    ig_id, token = os.environ["IG_USER_ID"], os.environ.get("IG_TOKEN") or os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    version = cfg.get("graph_api_version", "v23.0")
    size = Path(video_path).stat().st_size
    cid = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data={
        "media_type": "STORIES", "upload_type": "resumable", "access_token": token}))["id"]
    with open(video_path, "rb") as f:
        _check(requests.post(f"https://rupload.facebook.com/ig-api-upload/{version}/{cid}", data=f,
                             timeout=600, headers={"Authorization": f"OAuth {token}",
                                                   "offset": "0", "file_size": str(size)}))
    _wait_ig(g, cid, token)
    pub = _check(requests.post(f"{g}/{ig_id}/media_publish", timeout=60,
                               data={"creation_id": cid, "access_token": token}))
    return {"story_id": pub.get("id")}


def story_instagram_photo(cfg, image_url):
    ig_id, token = os.environ["IG_USER_ID"], os.environ.get("IG_TOKEN") or os.environ["FB_PAGE_TOKEN"]
    g = _graph(cfg)
    cid = _check(requests.post(f"{g}/{ig_id}/media", timeout=60, data={
        "media_type": "STORIES", "image_url": image_url, "access_token": token}))["id"]
    _wait_ig(g, cid, token, tries=15)
    pub = _check(requests.post(f"{g}/{ig_id}/media_publish", timeout=60,
                               data={"creation_id": cid, "access_token": token}))
    return {"story_id": pub.get("id")}

