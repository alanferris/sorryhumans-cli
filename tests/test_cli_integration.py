"""Integration smoke test of the CLI against the in-memory backend.

Starts the real backend (uvicorn on localhost) and exercises the CLI's client.py:
  - device_code / device_token (full flow with ALLOW_FAKE_AUTH)
  - register + list_agents
  - send + listen_once (incluyendo tipos ack/progress)

No mocks: validates that the CLI's HTTP client talks correctly to the bus.
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
# Python from the backend's venv -- isolated from the CLI to avoid a starlette 0.41 vs 1.x conflict
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
    raise RuntimeError(f"Backend did not come up in {timeout}s")


@pytest.fixture(scope="session")
def backend():
    """Start the backend with its own venv's Python, without mixing deps with the CLI."""
    if not BACKEND_DIR:
        pytest.skip("BACKEND_DIR is not set -- skipping integration tests")
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


# ── helpers to simulate the browser (ALLOW_FAKE_AUTH) ────────────────────────

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


# ── import the CLI client ───────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import client as cli_client


# ── tests ─────────────────────────────────────────────────────────────────────

def test_device_flow_full(backend):
    """Full flow device_code -> approve (fake browser) -> device_token -> api_key."""
    # 1. CLI asks for a code
    codes = cli_client.device_code(backend, machine_hint="ci-runner", role="agent")
    assert "device_code" in codes and "user_code" in codes

    # 2. Polling before approval -> 428
    status, data = cli_client.device_token(backend, codes["device_code"])
    assert status == 428
    assert data.get("status") == "pending"

    # 3. Simulate the browser: login + create project + approve
    ut = _browser_login(backend, "ci@sorryhumans.dev", "ci-sub")
    pid = _browser_create_project(backend, ut, "ci-project")
    _browser_approve(backend, ut, codes["user_code"], pid)

    # 4. Now the CLI obtains the api_key
    status, data = cli_client.device_token(backend, codes["device_code"])
    assert status == 200, data
    assert data["api_key"].startswith("am_live_")
    # Bus role policy: the owner who creates the project and connects their FIRST
    # machine becomes 'leader' (their other machines and all members are 'agent').
    assert data["role"] == "leader"


def test_register_and_list_agents(backend):
    """register is idempotent + list_agents returns the agent with its role."""
    # Bootstrap: team via device flow
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

    # list_agents shows the role
    agents = cli_client.list_agents(backend, api_key)
    assert any(a["name"] == "ci-agent" and a.get("role") == "leader" for a in agents)


def test_send_and_listen(backend):
    """send (task + ack) and listen_once receive the correct messages."""
    # Two agents on the same team
    codes_a = cli_client.device_code(backend, machine_hint="agent-a", role="agent")
    ut = _browser_login(backend, "send@x.com", "send-sub")
    pid = _browser_create_project(backend, ut, "send-project")
    _browser_approve(backend, ut, codes_a["user_code"], pid)
    _, tok = cli_client.device_token(backend, codes_a["device_code"])
    api_key = tok["api_key"]

    a = cli_client.register(backend, api_key, "agent-a", []).get("agent_id")
    b = cli_client.register(backend, api_key, "agent-b", []).get("agent_id")

    # A sends a task to B
    msg = cli_client.send(backend, api_key, a, b, "task", "haz algo")
    task_id = msg["message_id"]

    # B listens (without waiting, since=0)
    resp = cli_client.listen_once(backend, api_key, b, "0")
    msgs = resp["messages"]
    assert any(m["type"] == "task" and m["message_id"] == task_id for m in msgs)

    # B replies with ack (ref = task_id)
    cli_client.send(backend, api_key, b, a, "ack", "recibido", ref=task_id)

    # A sees the ack in its queue
    resp_a = cli_client.listen_once(backend, api_key, a, "0")
    ack_msgs = [m for m in resp_a["messages"] if m["type"] == "ack"]
    assert len(ack_msgs) == 1
    assert ack_msgs[0]["ref"] == task_id


def test_result_threads_to_task_via_ref(backend):
    """G2 end-to-end: a `result` with ref=task_id reaches the sender, threaded to the task.
    This is what the MCP tool `reply(..., ref=...)` now preserves."""
    codes = cli_client.device_code(backend, machine_hint="thread-a", role="agent")
    ut = _browser_login(backend, "thread@x.com", "thread-sub")
    pid = _browser_create_project(backend, ut, "thread-project")
    _browser_approve(backend, ut, codes["user_code"], pid)
    _, tok = cli_client.device_token(backend, codes["device_code"])
    api_key = tok["api_key"]

    a = cli_client.register(backend, api_key, "thread-a", []).get("agent_id")
    b = cli_client.register(backend, api_key, "thread-b", []).get("agent_id")

    # A sends a task to B; B replies with a result with ref = task_id
    task = cli_client.send(backend, api_key, a, b, "task", "do x")
    task_id = task["message_id"]
    cli_client.send(backend, api_key, b, a, "result", "did x", ref=task_id)

    # A sees the result threaded to its original task
    resp_a = cli_client.listen_once(backend, api_key, a, "0")
    results = [m for m in resp_a["messages"] if m["type"] == "result"]
    assert any(m.get("ref") == task_id for m in results), \
        "the result must arrive with ref=task_id (threading)"


def test_invalid_key_is_rejected(backend):
    """The bus rejects an invalid key (401/403) -- the path that now makes VISIBLE
    the Monitor instead of spinning in silence (G3)."""
    r = requests.get(f"{backend}/v1/agents",
                     headers={"Authorization": "Bearer am_live_boguskey"})
    assert r.status_code in (401, 403)


def test_read_receipts_end_to_end(backend):
    """Full ladder against the real bus: sent -> delivered (B pulls) -> read (B marks),
    and sender A sees it via message_status."""
    codes = cli_client.device_code(backend, machine_hint="rcpt-a", role="agent")
    ut = _browser_login(backend, "rcpt@x.com", "rcpt-sub")
    pid = _browser_create_project(backend, ut, "rcpt-project")
    _browser_approve(backend, ut, codes["user_code"], pid)
    _, tok = cli_client.device_token(backend, codes["device_code"])
    api_key = tok["api_key"]

    a = cli_client.register(backend, api_key, "rcpt-a", []).get("agent_id")
    b = cli_client.register(backend, api_key, "rcpt-b", []).get("agent_id")

    # Sent: A -> B
    mid = cli_client.send(backend, api_key, a, b, "task", "do x")["message_id"]
    st0 = cli_client.message_status(backend, api_key, mid)
    assert st0["delivered"] == {} and st0["read"] == {}    # ✓ sent only

    # Delivered: B's machine pulls its messages
    cli_client.listen_once(backend, api_key, b, "0")
    st1 = cli_client.message_status(backend, api_key, mid)
    assert b in st1["delivered"] and b not in st1["read"]   # ✓✓ delivered

    # Read: B surfaces it to its human and marks it
    cli_client.mark_read(backend, api_key, mid, b)
    st2 = cli_client.message_status(backend, api_key, mid)
    assert b in st2["delivered"] and b in st2["read"]       # blue ✓✓ read
