"""Tests del comando `relay` (envío de mensajes al hive).

Gaps que cubre (regresión):
  - relay imprimía NADA: el dev no sabía si el mensaje salió. Ahora confirma.
  - `--to <nombre>` se mandaba literal sin resolver a id (a diferencia del MCP). Ahora
    resuelve nombre→id vía list_agents.
  - sin credenciales -> error limpio con guía, nunca traceback.

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
    """Reemplaza client.send por un capturador; devuelve el dict con lo enviado."""
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
    assert "Sent to your team." in out          # confirmación visible (antes: nada)
    assert calls["to_agent"] is None            # sin --to => broadcast
    assert calls["body"] == "ping"
    assert calls["msg_type"] == "chat"


def test_relay_to_resolves_name_to_id(monkeypatch, capsys):
    _creds(monkeypatch)
    monkeypatch.setattr(client, "list_agents",
                        lambda base, key: [{"name": "agent@box", "agent_id": "a_box"}])
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(to="agent@box", body="hi"))
    assert calls["to_agent"] == "a_box"          # resolvió nombre→id
    out = capsys.readouterr().out
    assert "Sent to agent@box." in out           # confirma con el nombre amistoso


def test_relay_to_unknown_name_passes_through(monkeypatch, capsys):
    """Si el nombre no está en el hive, se manda tal cual (el bus decide); no rompe."""
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
    """Un 'result' sin --ref falla claro (el bus lo exige) ANTES de pegarle a la red."""
    _creds(monkeypatch)
    sent = []
    monkeypatch.setattr(client, "send", lambda *a, **k: sent.append(1))
    try:
        cli.cmd_relay(_args(type="result", body="done", ref=None))
        assert False, "debió salir"
    except SystemExit as e:
        assert e.code == 1
    assert sent == []          # ni siquiera intentó enviar


def test_relay_result_with_ref_ok(monkeypatch):
    _creds(monkeypatch)
    calls = _record_send(monkeypatch)
    cli.cmd_relay(_args(type="result", body="done", ref="m_task1"))
    assert calls["msg_type"] == "result" and calls["ref"] == "m_task1"


def test_relay_no_config_errors_clean(monkeypatch):
    """Sin api_key (ni env) -> SystemExit con guía 'sorryhumans connect', no traceback."""
    monkeypatch.setattr(config, "active", lambda: {})
    monkeypatch.delenv("SORRYHUMANS_KEY", raising=False)
    try:
        cli.cmd_relay(_args())
        assert False, "debió salir con error"
    except SystemExit as e:
        assert "connect" in str(e.code)
