"""Resilience tests for `listen` (the SPINE: the Monitor runs `listen --follow`).

Gaps covered (regression):
  - G3: on a revoked/invalid key (401/403) the loop spun in SILENCE forever --
    the machine went deaf without warning. Now it emits ONE clear event and exits != 0.
  - transient network errors keep retrying (they don't kill the spine).
  - you don't wake on your own messages.
  - G5: the Monitor event shows the sender's NAME, not the raw id.
  - the cursor is persisted (per active project) so old messages aren't re-sent.

Offline: client.listen_once / list_agents y config se mockean; cero red. time.sleep
is neutralized so retries don't wait.
"""
import os
import sys
import time as _time
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli, config, client


class _Resp:
    def __init__(self, status):
        self.status_code = status


class _HTTPErr(Exception):
    """Imita requests.HTTPError: lleva .response.status_code."""
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.response = _Resp(status)


def _creds(monkeypatch):
    monkeypatch.setattr(config, "require_active",
                        lambda k, e=None: "am_live_x" if k == "api_key" else "a_self")
    monkeypatch.setattr(config, "get_active", lambda k, e=None: None)
    monkeypatch.setattr(config, "active", lambda: {})
    monkeypatch.setattr(config, "save_active", lambda d: None)
    monkeypatch.setattr(_time, "sleep", lambda s: None)  # no waiting between retries


def _seq_listen(monkeypatch, items):
    """client.listen_once returns each item in order; if it's an Exception, it raises it."""
    box = list(items)

    def fake(*a, **k):
        v = box.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(client, "listen_once", fake)


def test_auth_failure_emits_event_and_exits(monkeypatch, capsys):
    """401 -> one clear line (a Monitor event) + exit != 0; never infinite silence."""
    _creds(monkeypatch)
    _seq_listen(monkeypatch, [_HTTPErr(401)])
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=True))
        assert False, "should have exited"
    except SystemExit as e:
        assert e.code == 2
    out = capsys.readouterr().out
    assert "revoked" in out
    assert "sorryhumans connect" in out


def test_403_also_treated_as_auth_failure(monkeypatch, capsys):
    _creds(monkeypatch)
    _seq_listen(monkeypatch, [_HTTPErr(403)])
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=True))
        assert False
    except SystemExit as e:
        assert e.code == 2


def test_transient_error_retries_then_delivers(monkeypatch, capsys):
    """A network hiccup is NOT an auth-fail: it retries and delivers the next message."""
    _creds(monkeypatch)
    batch = {"messages": [{"from_agent": "a_other", "type": "chat", "body": "hi"}],
             "cursor": "5"}
    _seq_listen(monkeypatch, [RuntimeError("name resolution"), batch])
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=False))  # non-follow: exits on the 1st batch
        assert False
    except SystemExit as e:
        assert e.code == 0
    assert "hi" in capsys.readouterr().out


def test_follow_skips_own_and_resolves_names(monkeypatch, capsys):
    """G5: your own message is ignored; others show with a NAME, not the raw id.
    After delivering the batch, a 401 ends the loop (follow doesn't exit on its own)."""
    _creds(monkeypatch)
    batch = {"messages": [
        {"from_agent": "a_self", "type": "chat", "body": "mine"},
        {"from_agent": "a_other", "type": "task", "body": "theirs"},
    ], "cursor": "9"}
    monkeypatch.setattr(client, "list_agents",
                        lambda *a, **k: [{"agent_id": "a_other", "name": "agent@box"}])
    _seq_listen(monkeypatch, [batch, _HTTPErr(401)])
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=True))
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "theirs" in out
    assert "mine" not in out          # own: you don't wake on it
    assert "agent@box" in out         # readable name (G5)
    assert "a_other" not in out       # id crudo reemplazado


def test_cursor_is_persisted(monkeypatch):
    """The advanced cursor is saved (via save_active) to avoid re-sending old ones."""
    saved = {}
    monkeypatch.setattr(config, "require_active",
                        lambda k, e=None: "am" if k == "api_key" else "a_self")
    monkeypatch.setattr(config, "get_active", lambda k, e=None: None)
    monkeypatch.setattr(config, "active", lambda: {})
    monkeypatch.setattr(config, "save_active", lambda d: saved.update(d))
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    batch = {"messages": [{"from_agent": "a_other", "type": "chat", "body": "x"}],
             "cursor": "42"}
    monkeypatch.setattr(client, "listen_once", lambda *a, **k: batch)
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=False))
    except SystemExit:
        pass
    assert saved.get("listen_cursor") == "42"
