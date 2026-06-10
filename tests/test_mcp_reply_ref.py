"""Tests for result threading in the MCP (`reply` with `ref`).

Gap covered (G2, regression): the `reply` tool sent the result WITHOUT `ref`, so the
agent that sent the `task` couldn't correlate the answer. Now `_send` propagates
`ref` to the bus payload (same as the field check_messages returns).

Offline: httpx.AsyncClient is mocked; zero network. The exact outgoing payload is checked.
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
    """Captures the last POST in _FakeClient.last_post."""
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
    monkeypatch.setattr(mcp_server, "KEY", "am_test")      # _headers requires KEY
    mcp_server._state["agent_id"] = "a_self"               # avoids the network register
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", _FakeClient)
    _FakeClient.last_post = None


def test_result_includes_ref_and_resolves_name(monkeypatch):
    _setup(monkeypatch)
    asyncio.run(mcp_server._send("agent@box", "result body", "result", ref="m_task1"))
    p = _FakeClient.last_post
    assert p["ref"] == "m_task1"          # threads the result to the original task
    assert p["to_agent"] == "a_box"       # resolved name->id
    assert p["type"] == "result"
    assert p["body"] == "result body"


def test_send_without_ref_omits_key(monkeypatch):
    """Without ref (e.g. a chat/broadcast) the 'ref' key is NOT put in the payload."""
    _setup(monkeypatch)
    asyncio.run(mcp_server._send(None, "hi team", "task"))
    p = _FakeClient.last_post
    assert "ref" not in p
    assert p["to_agent"] is None          # broadcast (everyone)
    assert p["type"] == "task"
