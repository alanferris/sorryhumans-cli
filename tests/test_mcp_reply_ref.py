"""Tests del threading de results en el MCP (`reply` con `ref`).

Gap que cubre (G2, regresión): la tool `reply` mandaba el result SIN `ref`, así que el
agente que envió el `task` no podía correlacionar la respuesta. Ahora `_send` propaga
`ref` al payload del bus (igual que el campo que devuelve check_messages).

Offline: se mockea httpx.AsyncClient; cero red. Se valida el payload exacto que sale.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import mcp_server


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


class _FakeClient:
    """Captura el último POST en _FakeClient.last_post."""
    last_post = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        return _FakeResp({"agents": [{"name": "agent@box", "agent_id": "a_box"}]})

    async def post(self, url, headers=None, json=None):
        _FakeClient.last_post = json
        return _FakeResp({"message_id": "m_new"})


def _setup(monkeypatch):
    monkeypatch.setattr(mcp_server, "KEY", "am_test")      # _headers exige KEY
    mcp_server._state["agent_id"] = "a_self"               # evita el register de red
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", _FakeClient)
    _FakeClient.last_post = None


def test_result_includes_ref_and_resolves_name(monkeypatch):
    _setup(monkeypatch)
    asyncio.run(mcp_server._send("agent@box", "result body", "result", ref="m_task1"))
    p = _FakeClient.last_post
    assert p["ref"] == "m_task1"          # enlaza el result con el task original
    assert p["to_agent"] == "a_box"       # resolvió nombre→id
    assert p["type"] == "result"
    assert p["body"] == "result body"


def test_send_without_ref_omits_key(monkeypatch):
    """Sin ref (p. ej. un chat/broadcast) NO se mete la clave 'ref' en el payload."""
    _setup(monkeypatch)
    asyncio.run(mcp_server._send(None, "hola equipo", "task"))
    p = _FakeClient.last_post
    assert "ref" not in p
    assert p["to_agent"] is None          # broadcast (everyone)
    assert p["type"] == "task"
