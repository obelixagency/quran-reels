"""يطلعلك FB_PAGE_ID و FB_PAGE_TOKEN (مش بينتهي) و IG_USER_ID.

الاستخدام:
  python tools/setup_meta.py

SHORT_LIVED_USER_TOKEN تجيبه من Graph API Explorer بالصلاحيات دي:
  pages_show_list, pages_read_engagement, pages_manage_posts, business_management,
  instagram_basic, instagram_content_publish
"""
import sys
from getpass import getpass
from secure_handoff import local_only, write_credentials

import requests

V = "v23.0"


def main():
    local_only()
    app_id, secret, short = getpass("App ID: "), getpass("App secret: "), getpass("User token: ")
    r = requests.get(f"https://graph.facebook.com/{V}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
        "fb_exchange_token": short}, timeout=60).json()
    if "access_token" not in r:
        sys.exit("Authorization failed; provider details withheld")
    long_user = r["access_token"]

    pages = requests.get(f"https://graph.facebook.com/{V}/me/accounts", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "access_token": long_user}, timeout=60).json()
    if "data" not in pages:
        sys.exit("Authorization failed; provider details withheld")

    write_credentials({"pages": pages["data"]})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Setup failed; provider details withheld") from None

