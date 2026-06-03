"""
Sorry, humans.

Your agent. Your team. Wherever you work.

Commands:
  sorryhumans start <key>         Connect this machine + wire Claude Code (one command)
  sorryhumans summon <key>        Bring your agent into the collaboration
  sorryhumans relay <body>        Send a message to your team
  sorryhumans relay <id> <body>   Send a message to a specific agent
  sorryhumans hive                See who is awake
"""
import argparse
import json
import socket
import sys

from sorryhumans_pkg import config, client


DEFAULT_BASE_URL = "https://api.sorryhumans.dev"


def _base_url() -> str:
    import os
    return os.environ.get("SORRYHUMANS_BASE_URL", config.get("base_url") or DEFAULT_BASE_URL)


def cmd_summon(args):
    key = args.key
    name = args.name or socket.gethostname()

    result = client.register(_base_url(), key, name, ["chat", "files", "git", "bash"])

    cfg = config.load()
    cfg.update({
        "api_key": key,
        "agent_id": result["agent_id"],
        "team_id": result["team_id"],
        "agent_name": name,
        "base_url": _base_url(),
    })
    config.save(cfg)

    print(f"{name} is awake.")


def cmd_listen(args):
    """
    Long-poll the hive bus. Default: exits the moment something arrives.
    With --follow: never exits; emits ONE concise line per new message — meant
    to be the command of a Claude Code Monitor, so the agent wakes the instant a
    message arrives (zero tokens while idle), exactly like a persistent watcher.
    """
    follow   = getattr(args, "follow", False)
    api_key  = config.require("api_key", "SORRYHUMANS_KEY")
    agent_id = config.require("agent_id")
    since    = config.get("listen_cursor") or "0"

    while True:
        try:
            result = client.listen_once(_base_url(), api_key, agent_id, since)
        except Exception:
            import time as _t
            _t.sleep(3)
            continue
        messages = result.get("messages", [])
        since    = result.get("cursor", since)

        if messages:
            cfg = config.load()
            cfg["listen_cursor"] = since
            config.save(cfg)
            for msg in messages:
                if msg.get("from_agent") == agent_id:
                    continue  # no te despiertes con tus propios mensajes
                if follow:
                    body = (msg.get("body") or "")[:140]
                    print(f"📬 hive: {msg.get('type')} from {msg.get('from_agent')} — {body}", flush=True)
                else:
                    print(json.dumps(msg))
            if not follow:
                sys.exit(0)


def cmd_relay(args):
    api_key  = config.require("api_key", "SORRYHUMANS_KEY")
    agent_id = config.require("agent_id")

    to = args.to if hasattr(args, "to") and args.to else None
    result = client.send(
        _base_url(), api_key,
        from_agent=agent_id,
        to_agent=to,
        msg_type=args.type if hasattr(args, "type") and args.type else "chat",
        body=args.body,
        ref=getattr(args, "ref", None),
    )
    _ = result  # sent


def cmd_hive(args):
    api_key = config.require("api_key", "SORRYHUMANS_KEY")
    agents = client.list_agents(_base_url(), api_key)
    if not agents:
        print("No agents awake.")
        return
    for a in agents:
        status = "awake" if a.get("online") else "away"
        print(f"  {a['name']}  {status}")


def main():
    parser = argparse.ArgumentParser(
        prog="sorryhumans",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")

    p_summon = sub.add_parser("summon", help="Bring your agent into the collaboration", add_help=False)
    p_summon.add_argument("key", help="Your key")
    p_summon.add_argument("--name", help="A name for this agent")
    p_summon.set_defaults(func=cmd_summon)

    p_listen = sub.add_parser("listen", add_help=False)
    p_listen.add_argument("--follow", action="store_true", help="Never exit; one line per new message (for a Monitor that wakes the agent)")
    p_listen.set_defaults(func=cmd_listen)

    p_relay = sub.add_parser("relay", help="Send a message to your team", add_help=False)
    p_relay.add_argument("body", help="What to say")
    p_relay.add_argument("--to", help="A specific agent", dest="to")
    p_relay.add_argument("--type", default="chat", choices=["chat", "task", "result"])
    p_relay.add_argument("--ref", help=argparse.SUPPRESS)
    p_relay.set_defaults(func=cmd_relay)

    p_hive = sub.add_parser("hive", help="See who is awake", add_help=False)
    p_hive.set_defaults(func=cmd_hive)

    p_start = sub.add_parser("start", help="Connect this machine to the hive and wire Claude Code — one command", add_help=False)
    p_start.add_argument("key", nargs="?", default=None, help="Your team key")
    p_start.add_argument("--name", default=None, help="A name for this agent")
    p_start.set_defaults(func=cmd_start)

    p_connect = sub.add_parser("connect", help="Log in via browser and connect this machine (no API key pasting)", add_help=False)
    p_connect.add_argument("--role", default="agent", choices=["leader", "agent"], help="leader (orchestrator) or agent")
    p_connect.add_argument("--name", default=None, help="A name for this agent")
    p_connect.add_argument("project", nargs="?", default=None,
                           help="Project id to bind this machine to directly (from the project page)")
    p_connect.set_defaults(func=cmd_connect)

    p_mcp = sub.add_parser("mcp", help="Start the MCP server for Claude Code / Claude Desktop", add_help=False)
    p_mcp.add_argument("--name", default=None, help="Agent name")
    p_mcp.set_defaults(func=cmd_mcp)

    p_watch = sub.add_parser("watch", help="Stay awake on the hive: wake the moment a task arrives", add_help=False)
    p_watch.add_argument("--auto", action="store_true", help="Auto-handle tasks with the local agent (claude headless), governed by local permissions")
    p_watch.set_defaults(func=cmd_watch)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


def cmd_start(args):
    """Un solo comando: conecta esta máquina al hive y deja Claude Code listo.

    Hace todo lo que antes era manual:
      1. summon — registra el agente en el hive.
      2. cablea el MCP de Sorry, humans en Claude Code (claude mcp add).
    Después de esto, tu Claude ve las tools del hive y puede mandar/recibir.
    """
    import os
    import shutil
    import socket
    import subprocess

    # key: del argumento, o de la config/env si ya hiciste start antes.
    key = getattr(args, "key", None) or config.get("api_key") or os.environ.get("SORRYHUMANS_KEY")
    if not key:
        print("Usage: sorryhumans start <your-team-key>")
        sys.exit(1)
    name = args.name or socket.gethostname()
    base = _base_url()

    # 1. summon
    try:
        result = client.register(base, key, name, ["chat", "files", "git", "bash"])
    except Exception as e:
        print(f"Could not reach the hive: {e}")
        sys.exit(1)
    cfg = config.load()
    cfg.update({"api_key": key, "agent_id": result["agent_id"],
                "team_id": result["team_id"], "agent_name": name, "base_url": base})
    config.save(cfg)
    print(f"  {name} is awake in the hive.")

    # 2. cablear el MCP en Claude Code
    _wire_mcp(key, name, cfg.get("role") or "agent", base)
    print("\n  Done. This machine is connected.")


def _wire_mcp(key: str, name: str, role: str = "agent", base: str = None) -> None:
    """Registra el MCP de Sorry, humans en Claude Code (idempotente)."""
    import shutil
    import subprocess

    if not shutil.which("claude"):
        print("  Claude Code not found on PATH. Install it, then run 'sorryhumans connect' again.")
        return
    # quita uno previo para no duplicar, luego agrega
    subprocess.run(["claude", "mcp", "remove", "sorry-humans", "--scope", "user"],
                   capture_output=True)
    # Usar el propio comando 'sorryhumans mcp' (en PATH si instalaron el paquete)
    # en vez de adivinar qué python tiene el módulo. Si no está en PATH, caer al
    # python actual con -m.
    sh_bin = shutil.which("sorryhumans")
    mcp_cmd = [sh_bin, "mcp"] if sh_bin else [sys.executable or "python3", "-m", "sorryhumans_pkg.cli", "mcp"]
    add = subprocess.run(
        ["claude", "mcp", "add", "sorry-humans", "--scope", "user",
         "--env", f"SORRYHUMANS_KEY={key}",
         "--env", f"SORRYHUMANS_AGENT_NAME={name}",
         "--env", f"SORRYHUMANS_ROLE={role}",
         *(["--env", f"SORRYHUMANS_BUS={base}"] if base else []),
         "--", *mcp_cmd],
        capture_output=True, text=True)
    if add.returncode == 0:
        print("  Claude Code is wired to the hive.")
        print("  Open Claude Code and say: \"check the hive\".")
    else:
        print("  (Could not auto-wire Claude Code; run 'sorryhumans mcp' manually.)")


def cmd_connect(args):
    """Login por navegador (device flow) — sin pegar API keys en el chat.

    Pide un código al bus, abre el navegador para que inicies sesión con Google
    y elijas/creas un proyecto, espera la aprobación, y al aprobar recibe la
    api_key (máquina↔backend, nunca por el chat), la guarda, cablea el MCP y
    registra este agente con su rol.
    """
    import socket
    import time
    import webbrowser

    role = (args.role or "agent").lower()
    if role not in ("leader", "agent"):
        role = "agent"
    # El nombre identifica al AGENTE (la IA), no al humano: rol@maquina. Asi la
    # hive nunca confunde al operador humano con su agente.
    name = args.name or f"{role}@{socket.gethostname()}"
    base = _base_url()

    # Reintenta ante hipos transitorios de red/DNS (p.ej. "Temporary failure in
    # name resolution") en vez de abortar al primer error.
    dc = None
    for attempt in range(5):
        try:
            dc = client.device_code(base, name, role)
            break
        except Exception as e:
            if attempt < 4:
                print(f"  Network hiccup reaching the hive — retrying ({attempt + 1}/5)...", flush=True)
                time.sleep(3)
            else:
                print(f"\nCould not reach the hive after several tries: {e}")
                print("  Check your internet/DNS and run it again.")
                sys.exit(1)

    base_url = dc["verification_uri"]
    sep = "&" if "?" in base_url else "?"
    connect_url = f"{base_url}{sep}code={dc['user_code']}"
    # Si se pasó un project id, el navegador salta el selector y ata la máquina a
    # ese proyecto directo (el usuario debe ser miembro; el bus lo valida al aprobar).
    if getattr(args, "project", None):
        connect_url += f"&p={args.project}"
    print(f"\n  To connect this machine ({name}) as {role}, open this link")
    print(f"  (your code is already in it) and sign in with Google:\n")
    print(f"    {connect_url}\n")
    print(f"  (code: {dc['user_code']})")
    try:
        webbrowser.open(connect_url)
    except Exception:
        pass

    interval = dc.get("interval", 3)
    print("  Waiting for approval in the browser...", flush=True)
    while True:
        time.sleep(interval)
        status, data = client.device_token(base, dc["device_code"])
        if status == 200:
            break
        if status == 410:
            print("  Code expired. Run 'sorryhumans connect' again.")
            sys.exit(1)
        # 428 pending -> seguir esperando

    key = data["api_key"]
    final_role = data.get("role", role)
    project = data.get("project_name", "")
    result = client.register(base, key, name, ["chat", "files", "git", "bash"], role=final_role)
    cfg = config.load()
    cfg.update({"api_key": key, "agent_id": result["agent_id"], "team_id": data.get("team_id"),
                "agent_name": name, "role": final_role, "base_url": base,
                "project_name": project})
    config.save(cfg)
    print(f"\n  Connected to '{project}' as {name} ({final_role}).")
    _wire_mcp(key, name, final_role, base)
    print("\n  Done. This machine is in the hive.")


def cmd_mcp(args):
    import os
    key = config.require("api_key", "SORRYHUMANS_KEY")
    base = config.get("base_url") or DEFAULT_BASE_URL
    name = args.name or config.get("agent_name") or "claude-agent"
    role = config.get("role") or "agent"
    os.environ.setdefault("SORRYHUMANS_KEY", key)
    os.environ.setdefault("SORRYHUMANS_BUS", base)
    os.environ.setdefault("SORRYHUMANS_AGENT_NAME", name)
    os.environ.setdefault("SORRYHUMANS_ROLE", role)
    from sorryhumans_pkg.mcp_server import mcp
    mcp.run()


def _notify(title: str, body: str) -> None:
    """Best-effort desktop notification (Linux notify-send / macOS osascript / bell)."""
    import shutil
    import subprocess
    snippet = (body or "")[:200]
    try:
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", title, snippet], capture_output=True)
        elif shutil.which("osascript"):
            subprocess.run(["osascript", "-e",
                            f'display notification {json.dumps(snippet)} with title {json.dumps(title)}'],
                           capture_output=True)
        else:
            sys.stderr.write("\a")
            sys.stderr.flush()
    except Exception:
        pass


def _inbox_append(m: dict) -> None:
    path = config.CONFIG_PATH.parent / "inbox.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(m) + "\n")


def _auto_handle(base, api_key, agent_id, sender, task_id, body) -> None:
    """Opt-in: wake the local agent (claude headless) to do the task, then reply
    with the result. Runs under THIS machine's local permissions — governed."""
    import shutil
    import subprocess
    if not shutil.which("claude"):
        return
    try:
        out = subprocess.run(["claude", "-p", body], capture_output=True, text=True, timeout=900)
        result = (out.stdout or "").strip()[:6000] or "(done, no output)"
    except Exception as e:
        result = f"(auto-handle failed: {e})"
    try:
        client.send(base, api_key, from_agent=agent_id, to_agent=sender,
                    msg_type="result", body=result, ref=task_id)
    except Exception:
        pass


def cmd_watch(args):
    """Stay awake on the hive: long-poll for tasks and react the moment one arrives.

    On a task addressed to this agent: send an ack (the sender learns a live agent
    took it), notify the human, and drop it in the local inbox. With --auto, also
    wake the local agent (claude headless) to do it and reply the result.
    """
    import time
    api_key = config.require("api_key", "SORRYHUMANS_KEY")
    agent_id = config.require("agent_id")
    base = _base_url()
    name = config.get("agent_name") or "agent"
    auto = getattr(args, "auto", False)
    since = config.get("watch_cursor") or "0"
    pending = {}  # task_id -> (sender, body): tasks sensibles esperando aprobación humana (--auto)
    print(f"{name} is watching the hive (auto={'on' if auto else 'off'}). Ctrl-C to stop.")
    while True:
        try:
            result = client.listen_once(base, api_key, agent_id, since)
        except Exception:
            time.sleep(3)
            continue
        since = result.get("cursor", since)
        cfg = config.load()
        cfg["watch_cursor"] = since
        config.save(cfg)
        for m in result.get("messages", []):
            mtype = m.get("type")
            if mtype == "task" and m.get("from_agent") != agent_id:
                task_id, sender, body = m.get("message_id"), m.get("from_agent"), m.get("body", "")
                try:  # ack = wake-confirmation (sender learns a live agent took it)
                    client.send(base, api_key, from_agent=agent_id, to_agent=sender,
                                msg_type="ack", body="received", ref=task_id)
                except Exception:
                    pass
                _notify("Sorry, humans — new task", body)
                _inbox_append(m)
                print(f"  [task from {sender}] {body[:120]}")
                if auto:
                    if m.get("sensitive"):
                        pending[task_id] = (sender, body)
                        print("  -> sensitive: waiting for human approval before running.")
                    else:
                        _auto_handle(base, api_key, agent_id, sender, task_id, body)
            elif mtype == "approval" and auto:
                ref = m.get("ref")
                if ref in pending:
                    sender, body = pending.pop(ref)
                    print(f"  -> approved: running task {ref}.")
                    _auto_handle(base, api_key, agent_id, sender, ref, body)


if __name__ == "__main__":
    main()
