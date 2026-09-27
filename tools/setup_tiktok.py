"""يطلعلك TIKTOK_REFRESH_TOKEN (صالح لمدة سنة تقريبًا).

الاستخدام:
  python tools/setup_tiktok.py CLIENT_KEY CLIENT_SECRET REDIRECT_URI

REDIRECT_URI لازم يكون نفس اللي مسجّل في تطبيقك على developers.tiktok.com (Login Kit → Redirect URI)
مثال: https://<اسمك>.github.io/  أو أي رابط https تملكه.
"""
import secrets
import sys
import urllib.parse

import requests

SCOPES = "user.info.basic,video.upload,video.publish"


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    key, secret, redirect = sys.argv[1:]
    state = secrets.token_urlsafe(8)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key, "scope": SCOPES, "response_type": "code",
        "redirect_uri": redirect, "state": state})
    print("1) افتح الرابط ده في المتصفح وسجّل دخول بحساب التيك توك اللي هننشر عليه ووافق:\n")
    print(url)
    print("\n2) بعد الموافقة هيحوّلك لصفحة الـ Redirect. انسخ الرابط الكامل من شريط العنوان والصقه هنا:")
    back = input("> ").strip()
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
    if "code" not in qs:
        sys.exit(f"مفيش code في الرابط: {qs}")
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=60, data={
        "client_key": key, "client_secret": secret, "code": qs["code"][0],
        "grant_type": "authorization_code", "redirect_uri": redirect},
        headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
    if "refresh_token" not in r:
        sys.exit(f"فشل: {r}")
    print("\nTIKTOK_REFRESH_TOKEN =", r["refresh_token"])
    print("scopes:", r.get("scope"))


if __name__ == "__main__":
    main()
