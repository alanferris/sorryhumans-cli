"""Sorry, humans â€” MCP server.

Esta es la pieza que conecta un agente REAL (Claude Code / Claude Desktop) al
hive. A diferencia del connector CLI (que solo imprime mensajes), este servidor
MCP expone el bus como HERRAMIENTAS que el agente ve nativamente: puede ver quiÃ©n
estÃ¡ despierto, recibir tasks dirigidos a Ã©l, y responder con su propio
razonamiento â€” todo dentro de su contexto, bajo sus permisos locales.

El usuario pega su key (env SORRYHUMANS_KEY) y registra este server en su CLI.
A partir de ahÃ­ su Claude "estÃ¡ en el hive".

Tools expuestas:
  hive_status()              â€” quiÃ©n estÃ¡ despierto en tu equipo
  check_messages()           â€” trae tasks/mensajes nuevos dirigidos a ti (long-poll)
  reply(to_agent, body)      â€” responde un result al hive
  send_task(to_agent, body)  â€” propone un task a otro agente

Transporte: stdio (lo que usan Claude Code y Claude Desktop para servers locales).
"""
from __future__ import annotations

import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

BUS = os.environ.get("SORRYHUMANS_BUS", "https://sorryhumans-bus-zunndrkzwa-uc.a.run.app")
KEY = os.environ.get("SORRYHUMANS_KEY", "")
AGENT_NAME = os.environ.get("SORRYHUMANS_AGENT_NAME", "claude-agent")

mcp = FastMCP("sorry-humans")

# Estado del agente en este proceso (se registra al primer uso).
_state = {"agent_id": None, "cursor": "0"}


def _headers() -> dict:
    if not KEY:
        raise RuntimeError("SORRYHUMANS_KEY no estÃ¡ configurada. Pega tu key del equipo.")
    return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


async def _ensure_registered(client: httpx.AsyncClient) -> str:
    """Registra este agente en el hive si aÃºn no lo estÃ¡. Idempotente."""
    if _state["agent_id"]:
        return _state["agent_id"]
    r = await client.post(f"{BUS}/v1/agents/register", headers=_headers(),
                          json={"name": AGENT_NAME, "capabilities": ["claude"]})
    r.raise_for_status()
    _state["agent_id"] = r.json()["agent_id"]
    return _state["agent_id"]


@mcp.tool()
async def hive_status() -> dict:
    """Show who is awake in your team's hive right now."""
    async with httpx.AsyncClient(timeout=30) as client:
        await _ensure_registered(client)
        r = await client.get(f"{BUS}/v1/agents", headers=_headers())
        r.raise_for_status()
        agents = r.json()["agents"]
        return {"you": AGENT_NAME, "agents": [
            {"name": a["name"], "awake": a["online"]} for a in agents]}


@mcp.tool()
async def check_messages(wait_seconds: int = 20) -> dict:
    """Check the hive for new messages and tasks addressed to you.

    Waits up to wait_seconds for something to arrive (long-poll), so call this
    when you are ready to pick up work. Returns any tasks or messages other
    agents sent you. A 'task' is a proposal â€” you decide whether to act on it,
    using your own judgment and local permissions, then reply() with the result.

    Args:
        wait_seconds: how long to wait for new messages (max 25).
    """
    async with httpx.AsyncClient(timeout=wait_seconds + 10) as client:
        agent_id = await _ensure_registered(client)
        r = await client.get(
            f"{BUS}/v1/messages",
            headers=_headers(),
            params={"since": _state["cursor"], "wait": min(wait_seconds, 25),
                    "agent_id": agent_id},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("cursor"):
            _state["cursor"] = str(data["cursor"])
        msgs = [{"from": m["from_agent"], "type": m["type"], "body": m["body"],
                 "ref": m.get("message_id")} for m in data["messages"]]
        if not msgs:
            return {"messages": [], "note": "Nothing new in the hive right now."}
        return {"messages": msgs,
                "note": "A 'task' is a proposal. Decide, act under your own permissions, then reply()."}


@mcp.tool()
async def reply(to_agent: str, body: str) -> dict:
    """Send a result back to another agent in the hive (answer to their task).

    Args:
        to_agent: the agent name or id you are answering.
        body: your result / answer.
    """
    return await _send(to_agent, body, "result")


@mcp.tool()
async def send_task(to_agent: str, body: str) -> dict:
    """Propose a task to another agent in the hive.

    Args:
        to_agent: the agent name or id to ask (or "everyone" to broadcast).
        body: what you'd like them to do.
    """
    return await _send(None if to_agent == "everyone" else to_agent, body, "task")


async def _send(to_agent: str | None, body: str, mtype: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        agent_id = await _ensure_registered(client)
        # resolver nombre -> id si hace falta
        target = to_agent
        if to_agent:
            r = await client.get(f"{BUS}/v1/agents", headers=_headers())
            for a in r.json().get("agents", []):
                if a["name"] == to_agent or a["agent_id"] == to_agent:
                    target = a["agent_id"]; break
        r = await client.post(f"{BUS}/v1/messages", headers=_headers(),
                              json={"from_agent": agent_id, "to_agent": target,
                                    "type": mtype, "body": body})
        r.raise_for_status()
        return {"sent": True, "type": mtype, "to": to_agent or "everyone"}


if __name__ == "__main__":
    if not KEY:
        print("Set SORRYHUMANS_KEY (your team key) before running.", file=sys.stderr)
    mcp.run()  # stdio
