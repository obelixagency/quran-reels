"""يطلعلك FB_PAGE_ID و FB_PAGE_TOKEN (مش بينتهي) و IG_USER_ID.

الاستخدام:
  python tools/setup_meta.py APP_ID APP_SECRET SHORT_LIVED_USER_TOKEN

SHORT_LIVED_USER_TOKEN تجيبه من Graph API Explorer بالصلاحيات دي:
  pages_show_list, pages_read_engagement, pages_manage_posts, business_management,
  instagram_basic, instagram_content_publish
"""
import sys

import requests

V = "v23.0"


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    app_id, secret, short = sys.argv[1:]
    r = requests.get(f"https://graph.facebook.com/{V}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
        "fb_exchange_token": short}, timeout=60).json()
    if "access_token" not in r:
        sys.exit(f"Token exchange failed: {r}")
    long_user = r["access_token"]

    pages = requests.get(f"https://graph.facebook.com/{V}/me/accounts", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "access_token": long_user}, timeout=60).json()
    if "data" not in pages:
        sys.exit(f"Could not list pages: {pages}")

    for p in pages["data"]:
        ig = p.get("instagram_business_account") or {}
        print("=" * 60)
        print(f"Page: {p['name']}")
        print(f"  FB_PAGE_ID    = {p['id']}")
        print(f"  FB_PAGE_TOKEN = {p['access_token']}")
        if ig:
            print(f"  IG_USER_ID    = {ig['id']}   (@{ig.get('username', '')})")
        else:
            print("  ⚠️ مفيش حساب إنستجرام بيزنس مربوط بالصفحة دي")
    print("=" * 60)
    print("انسخ القيم دي وحطها في GitHub → Settings → Secrets and variables → Actions")


if __name__ == "__main__":
    main()
