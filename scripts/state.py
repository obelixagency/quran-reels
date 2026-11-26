"""State files (history, stats, …) live in Cloudflare Workers KV instead of being committed to git.

    python scripts/state.py pull            # at the start of a job: KV → working tree
    python scripts/state.py push FILE...    # at the end: changed files → KV

Every key is "quran-reels/<path>". A file that is not in KV yet is copied there from the repo the first
time any job runs (with an empty saved_at, so it never counts as a post). Each save stores
{"saved_at": <UTC time>} as the key's metadata; the watchdog uses it to see whether a slot was posted.
Nothing is committed to git any more: a job whose state cannot be loaded or saved fails loudly.

Exit codes: 0 ok · 3 KV not configured · 1 KV error.
Needs CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID (repo variables) and CF_API_TOKEN (secret). The token is
never printed.
"""
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "quran-reels/"
BASELINE = ROOT / ".state_pulled.json"   # sha1 of what the job started with (not committed)
NOT_CONFIGURED = 3

# every file a workflow used to commit after a run
FILES = ["history.json", "history_en.json", "shorts_history.json", "posts_history.json",
         "posts_history_en.json", "adhkar_history.json", "adhkar_history_en.json",
         "promoted_long.json", "stats.json", "insights_report.md"]


def config():
    acct, ns, tok = (os.getenv(k, "").strip() for k in ("CF_ACCOUNT_ID", "CF_KV_NAMESPACE_ID", "CF_API_TOKEN"))
    if not (acct and ns and tok):
        return None
    return f"https://api.cloudflare.com/client/v4/accounts/{acct}/storage/kv/namespaces/{ns}", \
        {"Authorization": f"Bearer {tok}"}


def key_url(base, kind, path):
    return f"{base}/{kind}/{quote(PREFIX + path, safe='')}"


def call(method, url, headers, tries=4, **kw):
    """HTTP with retries; returns the response for 2xx/404, raises otherwise. No secrets in messages."""
    last = None
    for i in range(tries):
        try:
            r = requests.request(method, url, headers=headers, timeout=60, **kw)
            if r.ok or r.status_code == 404:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (400, 401, 403):
                break   # retrying will not help (wrong token / permission)
        except requests.RequestException as e:
            last = type(e).__name__
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"Cloudflare KV {method} failed: {last}")


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def pull(files=FILES):
    cfg = config()
    if not cfg:
        print("::error::Cloudflare KV is not configured (CF_ACCOUNT_ID / CF_KV_NAMESPACE_ID / CF_API_TOKEN)")
        return NOT_CONFIGURED
    base, h = cfg
    baseline = {}
    for f in files:
        p = ROOT / f
        r = call("GET", key_url(base, "values", f), h)
        if r.status_code == 404:
            if not p.exists():
                src = "not in KV, not in the repo"
            else:   # first time: copy the repo file to KV (empty saved_at = not a post)
                call("PUT", key_url(base, "values", f), h,
                     files={"value": (f, p.read_bytes(), "application/octet-stream"),
                            "metadata": (None, json.dumps({"saved_at": "", "seeded": "repo"}))})
                src = "copied from the repo to KV"
        else:
            p.write_bytes(r.content)
            src = "KV"
        baseline[f] = sha1(p.read_bytes()) if p.exists() else None
        print(f"  {f}: {src}")
    BASELINE.write_text(json.dumps(baseline))
    return 0


def push(files):
    cfg = config()
    if not cfg:
        print("::error::Cloudflare KV is not configured (CF_ACCOUNT_ID / CF_KV_NAMESPACE_ID / CF_API_TOKEN)")
        return NOT_CONFIGURED
    base, h = cfg
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    for f in files:
        p = ROOT / f
        if not p.exists():
            continue
        data = p.read_bytes()
        if baseline.get(f) == sha1(data):
            print(f"  {f}: unchanged")
            continue
        meta = {"saved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run": os.getenv("GITHUB_RUN_ID", "")}
        call("PUT", key_url(base, "values", f), h,
             files={"value": (f, data, "application/octet-stream"), "metadata": (None, json.dumps(meta))})
        # read it back so a broken save never passes silently
        back = call("GET", key_url(base, "values", f), h)
        if back.status_code == 404 or sha1(back.content) != sha1(data):
            raise RuntimeError(f"{f}: read-back from KV does not match what was saved")
        baseline[f] = sha1(data)
        print(f"  {f}: saved to KV ({len(data):,} bytes)")
    BASELINE.write_text(json.dumps(baseline))
    return 0


def saved_at(f):
    """UTC time of the last save of FILE to KV, or None (not configured / never saved to KV)."""
    cfg = config()
    if not cfg:
        return None
    base, h = cfg
    r = call("GET", key_url(base, "metadata", f), h)
    if r.status_code == 404:
        return None
    ts = ((r.json() or {}).get("result") or {}).get("saved_at")
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) if ts else None


def main(argv):
    if not argv or argv[0] not in ("pull", "push"):
        print(__doc__)
        return 2
    try:
        return pull(argv[1:] or FILES) if argv[0] == "pull" else push(argv[1:])
    except RuntimeError as e:
        print(f"::error::{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
