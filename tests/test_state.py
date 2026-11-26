"""State in Cloudflare KV instead of git (scripts/state.py) + the watchdog reading save times from it."""
import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import state  # noqa: E402


class Resp:
    def __init__(self, status=200, content=b"", js=None):
        self.status_code, self.content, self._js = status, content, js

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._js


class FakeKV:
    """Minimal in-memory Workers KV REST API."""

    def __init__(self):
        self.values, self.meta, self.calls = {}, {}, []

    def __call__(self, method, url, headers=None, timeout=None, files=None, **kw):
        assert headers["Authorization"] == "Bearer TOKEN"
        kind, key = url.split("/")[-2], url.split("/")[-1]
        self.calls.append((method, kind, key))
        if method == "PUT":
            self.values[key] = files["value"][1]
            self.meta[key] = json.loads(files["metadata"][1])
            return Resp(200, js={"success": True})
        if key not in self.values:
            return Resp(404)
        if kind == "metadata":
            return Resp(200, js={"success": True, "result": self.meta.get(key)})
        return Resp(200, self.values[key])


@pytest.fixture
def kv(monkeypatch, tmp_path):
    fake = FakeKV()
    monkeypatch.setattr(state.requests, "request", fake)
    monkeypatch.setattr(state, "ROOT", tmp_path)
    monkeypatch.setattr(state, "BASELINE", tmp_path / ".state_pulled.json")
    monkeypatch.setattr(state.time, "sleep", lambda s: None)
    for k, v in {"CF_ACCOUNT_ID": "acct", "CF_KV_NAMESPACE_ID": "ns", "CF_API_TOKEN": "TOKEN"}.items():
        monkeypatch.setenv(k, v)
    return fake, tmp_path


KEY = "quran-reels%2Fhistory.json"


def test_not_configured_fails(monkeypatch, capsys):
    monkeypatch.delenv("CF_API_TOKEN", raising=False)
    assert state.main(["pull"]) == state.NOT_CONFIGURED
    assert state.main(["push", "history.json"]) == state.NOT_CONFIGURED
    assert "::error::" in capsys.readouterr().out


def test_first_run_copies_repo_file_to_kv_without_counting_as_a_post(kv):
    fake, root = kv
    (root / "history.json").write_text('{"posts": [1]}')
    assert state.main(["pull", "history.json"]) == 0
    assert (root / "history.json").read_text() == '{"posts": [1]}'      # repo copy kept locally
    assert fake.values[KEY] == b'{"posts": [1]}'                        # ... and copied to KV
    assert state.saved_at("history.json") is None                       # not a post
    puts = len([c for c in fake.calls if c[0] == "PUT"])
    assert state.main(["push", "history.json"]) == 0
    assert len([c for c in fake.calls if c[0] == "PUT"]) == puts        # unchanged -> no write
    (root / "history.json").write_text('{"posts": [1, 2]}')
    assert state.main(["push", "history.json"]) == 0
    assert fake.values[KEY] == b'{"posts": [1, 2]}'
    assert fake.meta[KEY]["saved_at"].endswith("Z")


def test_pull_overwrites_with_kv_and_push_skips_unchanged(kv):
    fake, root = kv
    fake.values[KEY] = b'{"posts": ["from kv"]}'
    (root / "history.json").write_text('{"posts": ["stale repo copy"]}')
    assert state.main(["pull", "history.json"]) == 0
    assert (root / "history.json").read_bytes() == b'{"posts": ["from kv"]}'
    assert state.main(["push", "history.json"]) == 0
    assert not [c for c in fake.calls if c[0] == "PUT"]


def test_kv_error_fails_loudly_without_leaking_the_token(kv, capsys):
    fake, root = kv
    state.requests.request = lambda *a, **k: Resp(403)
    assert state.main(["pull", "history.json"]) == 1
    out = capsys.readouterr().out
    assert "HTTP 403" in out and "TOKEN" not in out


def test_saved_at(kv):
    fake, root = kv
    assert state.saved_at("history.json") is None
    fake.values[KEY], fake.meta[KEY] = b"{}", {"saved_at": "2026-11-27T16:50:00Z"}
    assert state.saved_at("history.json") == dt.datetime(2026, 11, 27, 16, 50, tzinfo=dt.timezone.utc)


def test_watchdog_counts_a_kv_save_as_posted(kv, monkeypatch):
    fake, root = kv
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GH_TOKEN", "x")
    wd = importlib.import_module("watchdog")
    fake.values[KEY], fake.meta[KEY] = b"{}", {"saved_at": "2026-11-27T16:50:00Z"}
    since = dt.datetime(2026, 11, 27, 16, 32, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(wd.requests, "get", lambda *a, **k: pytest.fail("git check not needed"))
    assert wd.posted_since("history.json", since) is True
