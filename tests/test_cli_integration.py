"""Smoke test de integración del CLI contra el backend en memoria.

Arranca el backend real (uvicorn en localhost) y ejercita el client.py del CLI:
  - device_code / device_token (flujo completo con ALLOW_FAKE_AUTH)
  - register + list_agents
  - send + listen_once (incluyendo tipos ack/progress)

No usa mocks: valida que el cliente HTTP del CLI habla correctamente con el bus.
"""
import os
import subprocess
import sys
import time
import threading
import requests
import pytest

# ── fixtures ──────────────────────────────────────────────────────────────────

BACKEND_DIR = os.environ.get("BACKEND_DIR", "")
# Python del venv del backend — aislado del CLI para evitar conflicto starlette 0.41 vs 1.x
# (mcp[cli] → sse-starlette arrastra starlette 1.x; fastapi 0.115 requiere 0.41.x)
BACKEND_PYTHON = os.environ.get("BACKEND_PYTHON", sys.executable)
BASE_URL = "http://127.0.0.1:18765"


def _wait_ready(url: str, timeout: int = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"Backend no levantó en {timeout}s")


@pytest.fixture(scope="session")
def backend():
    """Levanta el backend con el Python de su propio venv, sin mezclar deps con el CLI."""
    if not BACKEND_DIR:
        pytest.skip("BACKEND_DIR no está definido — skipping integration tests")
    env = {**os.environ,
           "SORRYHUMANS_STORE": "memory",
           "ALLOW_FAKE_AUTH": "1",
           "PORT": "18765"}
    proc = subprocess.Popen(
        [BACKEND_PYTHON, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", "18765", "--log-level", "warning"],
        cwd=BACKEND_DIR,
        env=env,
    )
    try:
        _wait_ready(f"{BASE_URL}/health")
        yield BASE_URL
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ── helpers para simular el browser (ALLOW_FAKE_AUTH) ────────────────────────

def _browser_login(base_url: str, email: str, sub: str) -> str:
    r = requests.post(f"{base_url}/v1/auth/google",
                      json={"id_token": f"fake:{sub}:{email}:Test User"})
    assert r.status_code == 200, r.text
    return r.json()["user_token"]


def _browser_create_project(base_url: str, user_token: str, name: str) -> str:
    r = requests.post(f"{base_url}/v1/projects", json={"name": name},
                      headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _browser_approve(base_url: str, user_token: str, user_code: str, project_id: str):
    r = requests.post(f"{base_url}/v1/device/approve",
                      json={"user_code": user_code, "project_id": project_id},
                      headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200, r.text


# ── importar el cliente CLI ───────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import client as cli_client


# ── tests ─────────────────────────────────────────────────────────────────────

def test_device_flow_full(backend):
    """Flujo completo device_code → approve (browser fake) → device_token → api_key."""
    # 1. CLI pide código
    codes = cli_client.device_code(backend, machine_hint="ci-runner", role="agent")
    assert "device_code" in codes and "user_code" in codes

    # 2. Polling antes de aprobar → 428
    status, data = cli_client.device_token(backend, codes["device_code"])
    assert status == 428
    assert data.get("status") == "pending"

    # 3. Simular browser: login + crear proyecto + aprobar
    ut = _browser_login(backend, "ci@sorryhumans.dev", "ci-sub")
    pid = _browser_create_project(backend, ut, "ci-project")
    _browser_approve(backend, ut, codes["user_code"], pid)

    # 4. Ahora CLI obtiene la api_key
    status, data = cli_client.device_token(backend, codes["device_code"])
    assert status == 200, data
    assert data["api_key"].startswith("am_live_")
    # Política de roles del bus: el owner que crea el proyecto y conecta su PRIMERA
    # máquina queda 'leader' (las demás suyas y todos los miembros, 'agent').
    assert data["role"] == "leader"


def test_register_and_list_agents(backend):
    """register idempotente + list_agents devuelve el agente con su role."""
    # Bootstrap: equipo vía device flow
    codes = cli_client.device_code(backend, machine_hint="ci-agent", role="leader")
    ut = _browser_login(backend, "reg@x.com", "reg-sub")
    pid = _browser_create_project(backend, ut, "reg-project")
    _browser_approve(backend, ut, codes["user_code"], pid)
    _, tok = cli_client.device_token(backend, codes["device_code"])
    api_key = tok["api_key"]

    # Registrar agente
    reg1 = cli_client.register(backend, api_key, "ci-agent", ["bash"], role="leader")
    assert "agent_id" in reg1

    # Idempotencia: re-registrar = mismo agent_id
    reg2 = cli_client.register(backend, api_key, "ci-agent", ["bash"], role="leader")
    assert reg1["agent_id"] == reg2["agent_id"]

    # List_agents muestra el role
    agents = cli_client.list_agents(backend, api_key)
    assert any(a["name"] == "ci-agent" and a.get("role") == "leader" for a in agents)


def test_send_and_listen(backend):
    """send (task + ack) y listen_once reciben los mensajes correctos."""
    # Dos agentes en el mismo equipo
    codes_a = cli_client.device_code(backend, machine_hint="agent-a", role="agent")
    ut = _browser_login(backend, "send@x.com", "send-sub")
    pid = _browser_create_project(backend, ut, "send-project")
    _browser_approve(backend, ut, codes_a["user_code"], pid)
    _, tok = cli_client.device_token(backend, codes_a["device_code"])
    api_key = tok["api_key"]

    a = cli_client.register(backend, api_key, "agent-a", []).get("agent_id")
    b = cli_client.register(backend, api_key, "agent-b", []).get("agent_id")

    # A envía task a B
    msg = cli_client.send(backend, api_key, a, b, "task", "haz algo")
    task_id = msg["message_id"]

    # B escucha (sin esperar, since=0)
    resp = cli_client.listen_once(backend, api_key, b, "0")
    msgs = resp["messages"]
    assert any(m["type"] == "task" and m["message_id"] == task_id for m in msgs)

    # B responde con ack (ref = task_id)
    cli_client.send(backend, api_key, b, a, "ack", "recibido", ref=task_id)

    # A ve el ack en su cola
    resp_a = cli_client.listen_once(backend, api_key, a, "0")
    ack_msgs = [m for m in resp_a["messages"] if m["type"] == "ack"]
    assert len(ack_msgs) == 1
    assert ack_msgs[0]["ref"] == task_id


def test_result_threads_to_task_via_ref(backend):
    """G2 end-to-end: un `result` con ref=task_id llega al emisor enlazado al task.
    Esto es lo que la tool MCP `reply(..., ref=...)` ahora preserva."""
    codes = cli_client.device_code(backend, machine_hint="thread-a", role="agent")
    ut = _browser_login(backend, "thread@x.com", "thread-sub")
    pid = _browser_create_project(backend, ut, "thread-project")
    _browser_approve(backend, ut, codes["user_code"], pid)
    _, tok = cli_client.device_token(backend, codes["device_code"])
    api_key = tok["api_key"]

    a = cli_client.register(backend, api_key, "thread-a", []).get("agent_id")
    b = cli_client.register(backend, api_key, "thread-b", []).get("agent_id")

    # A manda task a B; B responde un result con ref = task_id
    task = cli_client.send(backend, api_key, a, b, "task", "do x")
    task_id = task["message_id"]
    cli_client.send(backend, api_key, b, a, "result", "did x", ref=task_id)

    # A ve el result enlazado a su task original
    resp_a = cli_client.listen_once(backend, api_key, a, "0")
    results = [m for m in resp_a["messages"] if m["type"] == "result"]
    assert any(m.get("ref") == task_id for m in results), \
        "el result debe llegar con ref=task_id (threading)"


def test_invalid_key_is_rejected(backend):
    """El bus rechaza una key inválida (401/403) — el camino que ahora vuelve VISIBLE
    el Monitor en vez de girar en silencio (G3)."""
    r = requests.get(f"{backend}/v1/agents",
                     headers={"Authorization": "Bearer am_live_boguskey"})
    assert r.status_code in (401, 403)
