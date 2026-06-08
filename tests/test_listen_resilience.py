"""Tests de resiliencia de `listen` (la ESPINA: el Monitor corre `listen --follow`).

Gaps que cubre (regresión):
  - G3: ante key revocada/inválida (401/403) el loop giraba en SILENCIO para siempre —
    la máquina quedaba sorda sin avisar. Ahora emite UN evento claro y sale ≠ 0.
  - errores transitorios de red siguen reintentando (no matan la espina).
  - no te despiertas con tus propios mensajes.
  - G5: el evento del Monitor muestra el NOMBRE del remitente, no el id crudo.
  - el cursor se persiste (por proyecto activo) para no reenviar mensajes viejos.

Offline: client.listen_once / list_agents y config se mockean; cero red. time.sleep
se neutraliza para que los reintentos no esperen.
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
    monkeypatch.setattr(_time, "sleep", lambda s: None)  # sin esperas en reintentos


def _seq_listen(monkeypatch, items):
    """client.listen_once devuelve cada item en orden; si es Exception, la lanza."""
    box = list(items)

    def fake(*a, **k):
        v = box.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(client, "listen_once", fake)


def test_auth_failure_emits_event_and_exits(monkeypatch, capsys):
    """401 -> una línea clara (evento del Monitor) + exit ≠ 0; nunca silencio infinito."""
    _creds(monkeypatch)
    _seq_listen(monkeypatch, [_HTTPErr(401)])
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=True))
        assert False, "debió salir"
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
    """Un hipo de red NO es auth-fail: reintenta y entrega el mensaje siguiente."""
    _creds(monkeypatch)
    batch = {"messages": [{"from_agent": "a_other", "type": "chat", "body": "hi"}],
             "cursor": "5"}
    _seq_listen(monkeypatch, [RuntimeError("name resolution"), batch])
    try:
        cli.cmd_listen(types.SimpleNamespace(follow=False))  # non-follow: sale al 1er batch
        assert False
    except SystemExit as e:
        assert e.code == 0
    assert "hi" in capsys.readouterr().out


def test_follow_skips_own_and_resolves_names(monkeypatch, capsys):
    """G5: el mensaje propio se ignora; el ajeno se muestra con NOMBRE, no id crudo.
    Tras entregar el batch, un 401 corta el loop (follow no sale solo)."""
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
    assert "mine" not in out          # propio: no te despiertas con él
    assert "agent@box" in out         # nombre legible (G5)
    assert "a_other" not in out       # id crudo reemplazado


def test_cursor_is_persisted(monkeypatch):
    """El cursor avanzado se guarda (vía save_active) para no reenviar lo viejo."""
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
