"""Sorry, humans API client — register, listen (long-poll), send."""
import sys
import time
import requests

DEFAULT_BASE_URL = "https://api.sorryhumans.dev"
LONG_POLL_WAIT = 25


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def register(base_url: str, api_key: str, name: str, capabilities: list,
             role: str = None) -> dict:
    """Register this agent. Idempotent — returns same agent_id on re-register."""
    payload = {"name": name, "capabilities": capabilities}
    if role:
        payload["role"] = role
    r = requests.post(
        f"{base_url}/v1/agents/register",
        json=payload,
        headers=_headers(api_key),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def device_code(base_url: str, machine_hint: str, role: str) -> dict:
    """Ask the bus for a device + user code (no auth). Start of the login flow."""
    r = requests.post(
        f"{base_url}/v1/device/code",
        json={"machine_hint": machine_hint, "role": role},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def device_token(base_url: str, device_code: str):
    """Poll for approval. Returns (status_code, data).
    200 = approved (data has api_key), 428 = pending, 410 = expired."""
    r = requests.post(
        f"{base_url}/v1/device/token",
        json={"device_code": device_code},
        timeout=10,
    )
    data = {}
    try:
        data = r.json()
    except Exception:
        pass
    return r.status_code, data


def listen_once(base_url: str, api_key: str, agent_id: str, since: str) -> dict:
    """
    Long-poll for messages. Blocks up to LONG_POLL_WAIT seconds.
    Returns {"messages": [...], "cursor": "<ts>"}.
    Shell waits for free; model only wakes when messages arrive.
    """
    r = requests.get(
        f"{base_url}/v1/messages",
        params={"since": since, "wait": LONG_POLL_WAIT, "agent_id": agent_id},
        headers=_headers(api_key),
        timeout=LONG_POLL_WAIT + 5,
    )
    r.raise_for_status()
    return r.json()


def send(base_url: str, api_key: str, from_agent: str, to_agent: str,
         msg_type: str, body: str, ref: str = None) -> dict:
    """Publish a message to the bus."""
    payload = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "type": msg_type,
        "body": body,
    }
    if ref:
        payload["ref"] = ref
    r = requests.post(
        f"{base_url}/v1/messages",
        json=payload,
        headers=_headers(api_key),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def list_agents(base_url: str, api_key: str) -> list:
    r = requests.get(f"{base_url}/v1/agents", headers=_headers(api_key), timeout=10)
    r.raise_for_status()
    return r.json().get("agents", [])


def mark_read(base_url: str, api_key: str, message_id: str, agent_id: str) -> dict:
    """Recibo 'leído' (✓✓ azul): `agent_id` se lo mostró a su humano."""
    r = requests.post(
        f"{base_url}/v1/messages/{message_id}/read",
        json={"agent_id": agent_id},
        headers=_headers(api_key),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def message_status(base_url: str, api_key: str, message_id: str) -> dict:
    """Estado de un mensaje (recibos delivered/read) — vista del emisor."""
    r = requests.get(
        f"{base_url}/v1/messages/{message_id}",
        headers=_headers(api_key),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
