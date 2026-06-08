"""Recibos en el lado CLI/MCP (offline, sin red).

- client.mark_read / message_status pegan al endpoint correcto.
- tool MCP mark_read: resuelve el agent_id propio y postea el ref; 404 -> nota limpia.
- tool MCP message_status: GET del mensaje; devuelve delivered/read.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import client, mcp_server


# ── client.py (requests mockeado) ────────────────────────────────────────────

class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._d = data or {}

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_client_mark_read_posts_to_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json)
        return _Resp(200, {"read": {"a_b": "t"}})

    monkeypatch.setattr(client.requests, "post", fake_post)
    out = client.mark_read("http://bus", "am_k", "m_1", "a_b")
    assert captured["url"] == "http://bus/v1/messages/m_1/read"
    assert captured["json"] == {"agent_id": "a_b"}
    assert out["read"] == {"a_b": "t"}


def test_client_message_status_gets_endpoint(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return _Resp(200, {"delivered": {}, "read": {}})

    monkeypatch.setattr(client.requests, "get", fake_get)
    client.message_status("http://bus", "am_k", "m_9")
    assert captured["url"] == "http://bus/v1/messages/m_9"


# ── tools MCP (httpx.AsyncClient mockeado) ───────────────────────────────────

class _AResp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._d = data or {}

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")


class _FakeAClient:
    last = None
    post_status = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAClient.last = ("POST", url, json)
        return _AResp(_FakeAClient.post_status,
                      {} if _FakeAClient.post_status >= 400 else {"read": {"a_self": "t"}})

    async def get(self, url, headers=None, params=None):
        _FakeAClient.last = ("GET", url, params)
        return _AResp(200, {"delivered": {"a_x": "t1"}, "read": {}})


def _setup(monkeypatch, post_status=200):
    monkeypatch.setattr(mcp_server, "KEY", "am_test")
    mcp_server._state["agent_id"] = "a_self"
    _FakeAClient.last = None
    _FakeAClient.post_status = post_status
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", _FakeAClient)


def test_mcp_mark_read_posts_with_own_agent_id(monkeypatch):
    _setup(monkeypatch)
    out = asyncio.run(mcp_server.mark_read("m_42"))
    method, url, body = _FakeAClient.last
    assert method == "POST" and url.endswith("/v1/messages/m_42/read")
    assert body == {"agent_id": "a_self"}        # resuelve su propio id
    assert out == {"read": True, "ref": "m_42"}


def test_mcp_mark_read_unknown_ref_returns_note(monkeypatch):
    _setup(monkeypatch, post_status=404)
    out = asyncio.run(mcp_server.mark_read("m_nope"))
    assert out["read"] is False and "unknown" in out["note"]


def test_mcp_message_status_gets_and_returns_receipts(monkeypatch):
    _setup(monkeypatch)
    out = asyncio.run(mcp_server.message_status("m_7"))
    method, url, _ = _FakeAClient.last
    assert method == "GET" and url.endswith("/v1/messages/m_7")
    assert out["delivered"] == {"a_x": "t1"} and out["read"] == {}
