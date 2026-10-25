"""يطلعلك TIKTOK_REFRESH_TOKEN (صالح لمدة سنة تقريبًا).

الاستخدام:
  python tools/setup_tiktok.py

REDIRECT_URI لازم يكون نفس اللي مسجّل في تطبيقك على developers.tiktok.com (Login Kit → Redirect URI)
مثال: https://<اسمك>.github.io/  أو أي رابط https تملكه.
"""
import secrets
import sys
from getpass import getpass
from secure_handoff import local_only, write_credentials
import urllib.parse

import requests

SCOPES = "user.info.basic,video.upload,video.publish"


def main():
    local_only()
    key, secret, redirect = getpass("Client key: "), getpass("Client secret: "), input("Redirect URI: ").strip()
    state = secrets.token_urlsafe(8)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key, "scope": SCOPES, "response_type": "code",
        "redirect_uri": redirect, "state": state})
    print("1) افتح الرابط ده في المتصفح وسجّل دخول بحساب التيك توك اللي هننشر عليه ووافق:\n")
    print(url)
    print("\n2) بعد الموافقة هيحوّلك لصفحة الـ Redirect. انسخ الرابط الكامل من شريط العنوان والصقه هنا:")
    back = getpass("Callback URL (hidden): ").strip()
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
    if "code" not in qs or qs.get("state", [None])[0] != state:
        sys.exit("Authorization failed; provider details withheld")
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=60, data={
        "client_key": key, "client_secret": secret, "code": qs["code"][0],
        "grant_type": "authorization_code", "redirect_uri": redirect},
        headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
    if "refresh_token" not in r:
        sys.exit("Authorization failed; provider details withheld")
    write_credentials({"TIKTOK_REFRESH_TOKEN": r["refresh_token"]})
    print("Authorization completed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Setup failed; provider details withheld") from None

