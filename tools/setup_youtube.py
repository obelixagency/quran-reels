"""يطلعلك YT_REFRESH_TOKEN و YT_CHANNEL_ID للقناة اللي هننشر عليها.

الاستخدام (على جهازك):
  python tools/setup_youtube.py

هيفتح المتصفح → سجّل دخول بحساب جوجل → اختار القناة المطلوبة (لو عندك أكتر من قناة) → وافق.
"""
import http.server
import secrets
import sys
from getpass import getpass
from secure_handoff import local_only, write_credentials
import urllib.parse
import webbrowser

import requests

SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
PORT = 8765


def main():
    local_only()
    client_id, client_secret = getpass("Client ID: "), getpass("Client secret: ")
    redirect = f"http://127.0.0.1:{PORT}/"
    state = secrets.token_urlsafe(10)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent select_account", "state": state})

    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in qs.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("تم ✅ ارجع للـ Terminal".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print("بيفتح المتصفح… لو مفتحش افتح الرابط ده:\n", url)
    webbrowser.open(url)
    while "code" not in result and "error" not in result:
        srv.handle_request()
    srv.server_close()
    if result.get("state") != state or "code" not in result:
        sys.exit("Authorization failed; provider details withheld")

    tok = requests.post("https://oauth2.googleapis.com/token", timeout=60, data={
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}).json()
    if "refresh_token" not in tok:
        sys.exit("Authorization failed; provider details withheld")
    ch = requests.get("https://www.googleapis.com/youtube/v3/channels",
                      params={"part": "id,snippet", "mine": "true"},
                      headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=60).json()
    item = (ch.get("items") or [{}])[0]
    print("\nالقناة:", item.get("snippet", {}).get("title"))
    print("YT_CHANNEL_ID    =", item.get("id"))
    write_credentials({"YT_REFRESH_TOKEN": tok["refresh_token"], "YT_CHANNEL_ID": item.get("id")})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Setup failed; provider details withheld") from None

