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
    Waits for the team. Exits the moment something arrives.
    Runs silently in the background â€” the agent wakes only when needed.
    """
    api_key  = config.require("api_key", "SORRYHUMANS_KEY")
    agent_id = config.require("agent_id")
    since    = config.get("listen_cursor") or "0"

    while True:
        result = client.listen_once(_base_url(), api_key, agent_id, since)
        messages = result.get("messages", [])
        cursor   = result.get("cursor", since)

        if messages:
            cfg = config.load()
            cfg["listen_cursor"] = cursor
            config.save(cfg)
            for msg in messages:
                print(json.dumps(msg))
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
    p_connect.set_defaults(func=cmd_connect)

    p_mcp = sub.add_parser("mcp", help="Start the MCP server for Claude Code / Claude Desktop", add_help=False)
    p_mcp.add_argument("--name", default=None, help="Agent name")
    p_mcp.set_defaults(func=cmd_mcp)

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
    name = args.name or socket.gethostname()
    base = _base_url()

    try:
        dc = client.device_code(base, name, role)
    except Exception as e:
        print(f"Could not reach the hive: {e}")
        sys.exit(1)

    base_url = dc["verification_uri"]
    sep = "&" if "?" in base_url else "?"
    connect_url = f"{base_url}{sep}code={dc['user_code']}"
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


if __name__ == "__main__":
    main()
