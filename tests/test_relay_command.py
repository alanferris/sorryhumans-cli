"""Tests for the `relay` command (sending messages to the hive).

Gaps covered (regression):
  - relay printed NOTHING: the dev didn't know if the message went out. Now it confirms.
  - `--to <name>` was sent literally without resolving to an id (unlike the MCP). Now
    it resolves name->id via list_agents.
  - no credentials -> clean error with guidance, never a traceback.

Todo offline: client.send / client.list_agents y config se mockean; cero red.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli, config, client


def _args(**kw):
    base = {"to": None, "type": "chat", "body": "hello", "ref": None}
    base.update(kw)
    return types.SimpleNamespace(**base)


def _record_send(monkeypatch):
    """Replace client.send with a capturer; returns the dict with what was sent."""
    calls = {}

    def fake(base, api_key, from_agent=None, to_agent=None, msg_type=None,
             body=None, ref=None):
        calls.update(dict(base=base, api_key=api_key, from_agent=from_agent,
                          to_agent=to_agent, msg_type=msg_type, body=body, ref=ref))
        return {"message_id": "m_new"}

    monkeypatch.setattr(client, "send", fake)
    return calls


def _creds(monkeypatch):
    monkeypatch.setattr(config, "require_active",
                        lambda k, e=None: "am_live_x" if k == "api_key" else "a_self")
    monkeypatch.setattr(config, "get_active", lambda k, e=None: None)  # base_url -> default


def test_relay_to_team_confirms_and_broadcasts(monkeypatch, capsys):
    _creds(monkeypatch)
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(body="ping"))
    out = capsys.readouterr().out
    assert "Sent to your team." in out          # visible confirmation (before: nothing)
    assert calls["to_agent"] is None            # no --to => broadcast
    assert calls["body"] == "ping"
    assert calls["msg_type"] == "chat"


def test_relay_to_resolves_name_to_id(monkeypatch, capsys):
    _creds(monkeypatch)
    monkeypatch.setattr(client, "list_agents",
                        lambda base, key: [{"name": "agent@box", "agent_id": "a_box"}])
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(to="agent@box", body="hi"))
    assert calls["to_agent"] == "a_box"          # resolved name->id
    out = capsys.readouterr().out
    assert "Sent to agent@box." in out           # confirms with the friendly name


def test_relay_to_unknown_name_passes_through(monkeypatch, capsys):
    """If the name isn't in the hive, it's sent as-is (the bus decides); no crash."""
    _creds(monkeypatch)
    monkeypatch.setattr(client, "list_agents", lambda base, key: [])
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(to="ghost", body="hi"))
    assert calls["to_agent"] == "ghost"
    assert "Sent to ghost." in capsys.readouterr().out


def test_relay_carries_type_and_ref(monkeypatch):
    _creds(monkeypatch)
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(type="result", body="done", ref="m_task1"))
    assert calls["msg_type"] == "result"
    assert calls["ref"] == "m_task1"


def test_relay_result_without_ref_errors(monkeypatch):
    """A 'result' without --ref fails clearly (the bus requires it) BEFORE hitting the network."""
    _creds(monkeypatch)
    sent = []
    monkeypatch.setattr(client, "send", lambda *a, **k: sent.append(1))
    try:
        cli.cmd_relay(_args(type="result", body="done", ref=None))
        assert False, "should have exited"
    except SystemExit as e:
        assert e.code == 1
    assert sent == []          # didn't even try to send


def test_relay_result_with_ref_ok(monkeypatch):
    _creds(monkeypatch)
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(type="result", body="done", ref="m_task1"))
    assert calls["msg_type"] == "result" and calls["ref"] == "m_task1"


def test_relay_no_config_errors_clean(monkeypatch):
    """No api_key (nor env) -> SystemExit with 'sorryhumans connect' guidance, no traceback."""
    monkeypatch.setattr(config, "active", lambda: {})
    monkeypatch.delenv("SORRYHUMANS_KEY", raising=False)
    try:
        cli.cmd_relay(_args())
        assert False, "should have exited with an error"
    except SystemExit as e:
        assert "connect" in str(e.code)
