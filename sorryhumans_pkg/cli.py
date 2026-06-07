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


def _force_utf8_output():
    """En Windows la consola por defecto es cp1252 y no puede codificar emojis (p. ej. el
    📬 de 'listen --follow'), lo que mata el Monitor con UnicodeEncodeError —y el Monitor
    es la columna del producto. Forzamos UTF-8 con errores tolerantes para que la salida
    nunca tumbe el proceso (degrada con '?' si la terminal no soporta el glifo)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _force_utf8_output()
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

    # Salida para el hook SessionStart de Claude Code (uso interno).
    p_hook = sub.add_parser("hook-context", add_help=False)
    p_hook.set_defaults(func=cmd_hook_context)

    p_use = sub.add_parser("use", help="Bind this directory to a project (multi-project)", add_help=False)
    p_use.add_argument("project", help="Project id to bind to this directory")
    p_use.set_defaults(func=cmd_use)

    p_disc = sub.add_parser("disconnect", help="Leave a project on this machine", add_help=False)
    p_disc.add_argument("project", nargs="?", default=None, help="Project id (default: the active one)")
    p_disc.set_defaults(func=cmd_disconnect)

    p_projects = sub.add_parser("projects", help="List your projects and open one", add_help=False)
    p_projects.set_defaults(func=cmd_projects)

    p_resume = sub.add_parser("resume", help="Resume your last Claude session in a project", add_help=False)
    p_resume.set_defaults(func=cmd_resume)

    p_setaut = sub.add_parser("set-autonomy", add_help=False)
    p_setaut.add_argument("project", nargs="?", default=None)
    p_setaut.add_argument("skip", nargs="?", default="1")
    p_setaut.set_defaults(func=cmd_set_autonomy)

    # Comando mal tecleado: en vez del 'invalid choice' seco de argparse, sugerir el
    # más parecido y ofrecer la lista de comandos como menú seleccionable.
    argv = sys.argv[1:]
    if "-h" not in argv and "--help" not in argv:
        first = next((a for a in argv if not a.startswith("-")), None)
        if first is not None and first not in sub.choices:
            chosen = _suggest_command(sub, first)
            if not chosen:
                sys.exit(1)
            sys.argv = [sys.argv[0], chosen]

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except KeyboardInterrupt:
        # Ctrl+C fuera de un prompt (p. ej. durante una llamada de red): salir limpio.
        sys.stderr.write("\n")
        sys.exit(130)


def _suggest_command(sub, typed):
    """Comando desconocido: muestra el más parecido + la lista de comandos de usuario
    como menú seleccionable. Devuelve el comando elegido, o None si se cancela."""
    import difflib
    cmds = [(a.dest, a.help or "") for a in sub._get_subactions()]  # solo los con help (de usuario)
    names = [c for c, _ in cmds]
    near = difflib.get_close_matches(typed, names, n=1, cutoff=0.5)
    if near:
        print(f"\n  '{typed}' isn't a command. Did you mean '{near[0]}'?")
    else:
        print(f"\n  '{typed}' isn't a command.")
    print("\n  Commands:\n")
    width = max((len(n) for n in names), default=0)
    for i, (name, help_) in enumerate(cmds, 1):
        print(f"    {i:>2}) {name:<{width}}  {help_}")
    default = str(names.index(near[0]) + 1) if near else ""
    hint = default if default else "number, or Enter to cancel"
    sel = _ask(f"\n  Run which? [{hint}]: ", default)
    if not sel:
        return None
    try:
        return cmds[int(sel) - 1][0]          # eligió por número
    except (ValueError, IndexError):
        return sel if sel in names else None   # o tecleó el nombre del comando


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
                "project_name": project, "member_uid": data.get("member_uid")})
    config.save(cfg)
    # Guardar también por-proyecto, para pertenecer a varios proyectos a la vez.
    if cfg.get("team_id"):
        config.save_project(cfg["team_id"], cfg)
    print(f"\n  Connected to '{project}' as {name} ({final_role}).")
    _wire_mcp(key, name, final_role, base)
    _wire_session_hook()
    print("\n  Done. This machine is in the hive.")


def _hook_command() -> str:
    """Comando del hook SessionStart: ruta COMPLETA al ejecutable real del venv —
    Scripts\\sorryhumans.exe en Windows, bin/sorryhumans en POSIX— citada por si el
    path del usuario tiene espacios. Si caemos a 'sorryhumans' a secas en Windows, éste
    resuelve a un binario SIN extensión y Claude Code, al correr el hook, dispara el
    diálogo "¿con qué app abrir esto?". La ruta completa al .exe lo evita."""
    import os
    venv = os.path.expanduser("~/.sorryhumans/venv")
    for c in (os.path.join(venv, "Scripts", "sorryhumans.exe"),  # Windows
              os.path.join(venv, "bin", "sorryhumans")):         # POSIX
        if os.path.exists(c):
            return f'"{c}" hook-context'
    return "sorryhumans hook-context"


def _wire_session_hook() -> None:
    """Instala un hook SessionStart en ~/.claude/settings.json que, al arrancar cada
    sesión de Claude Code, inyecta como directiva fuerte (additionalContext): armar el
    Monitor PRIMERO + el brief del proyecto (contexto global + instrucciones del miembro).
    El campo `instructions` del MCP es un canal débil; el hook es el más fuerte."""
    import os
    import json as _json
    sp = os.path.expanduser("~/.claude/settings.json")
    try:
        data = _json.load(open(sp)) if os.path.exists(sp) else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    cmd = _hook_command()
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = data["hooks"] = {}
    ss = hooks.setdefault("SessionStart", [])
    if not isinstance(ss, list):
        ss = hooks["SessionStart"] = []
    # Si ya hay un hook hook-context, CORREGIR su comando si difiere (p. ej. una
    # instalación vieja en Windows con la ruta sin .exe que disparaba el diálogo "abrir
    # con…"). Solo saltar si no hay que escribir nada. Antes esto se saltaba siempre que
    # existiera, así que un re-connect nunca reparaba instalaciones viejas.
    found = False
    changed = False
    for e in ss:
        if not isinstance(e, dict):
            continue
        for h in e.get("hooks", []):
            if isinstance(h, dict) and "hook-context" in h.get("command", ""):
                found = True
                if h.get("command") != cmd:
                    h["command"] = cmd
                    changed = True
    if not found:
        ss.append({"matcher": "startup",
                   "hooks": [{"type": "command", "command": cmd, "timeout": 15}]})
        changed = True
    if not changed:
        return
    try:
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        with open(sp, "w") as f:
            _json.dump(data, f, indent=2)
        msg = "updated" if found else "installed"
        print(f"  Session hook {msg} (arms the Monitor + loads your project brief at start).")
    except Exception:
        pass


def cmd_hook_context(args):
    """Salida para el hook SessionStart de Claude Code: directiva fuerte que ordena
    armar el Monitor primero y trae el brief del proyecto. SIEMPRE imprime JSON válido
    (best-effort: si el bus falla, igual emite el mandato del Monitor)."""
    import json as _json
    import urllib.request
    # El hook corre al arrancar CUALQUIER sesión de Claude Code (settings global).
    # Solo debe inyectar si ESTA sesión está atada explícitamente a un proyecto
    # (env SORRYHUMANS_PROJECT o marker .sorryhumans en cwd/padres). Sin binding NO
    # es una terminal del hive: emitimos additionalContext vacío y la dejamos limpia.
    if not config.active_project_id():
        print(_json.dumps({}))
        return
    cfg = config.active()   # proyecto activo: env > .sorryhumans (binding ya garantizado)
    key = cfg.get("api_key", "")
    team = cfg.get("team_id", "")
    uid = cfg.get("member_uid", "")
    base = cfg.get("base_url") or DEFAULT_BASE_URL
    monitor = (
        "SORRY, HUMANS — this machine is ALREADY connected to your hive (do NOT reconnect, do "
        "NOT re-run `sorryhumans connect` or the /sorryhumans connect skill). Your FIRST action this "
        "session, before replying or doing anything else, is to ARM a persistent Monitor that runs "
        "`sorryhumans listen --follow` (use the Monitor tool) so you wake on every hive message. "
        "Communication is the entire point of Sorry, humans: if that Monitor is not running this "
        "machine is deaf and disconnected. Nothing else proceeds until it is live; if arming it is "
        "declined, explain it is the spine of the connection and insist. Keep it alive the whole "
        "session and re-arm it immediately if it ever dies."
    )
    extra = ""
    if key and team:
        try:
            url = f"{base}/v1/projects/{team}/brief" + (f"?uid={uid}" if uid else "")
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
            d = _json.load(urllib.request.urlopen(req, timeout=8))
            if d.get("context"):
                extra += ("\n\nPROJECT CONTEXT (set by the project owner, applies to every agent "
                          "here — follow it): " + d["context"].strip())
            if d.get("instructions"):
                extra += ("\n\nYOUR INSTRUCTIONS (set by the owner specifically for you, this member "
                          "— follow them): " + d["instructions"].strip())
        except Exception:
            pass
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                  "additionalContext": monitor + extra}}
    print(_json.dumps(out))


def cmd_use(args):
    """Ata el directorio actual a un proyecto (escribe un marcador .sorryhumans).
    Abrir Claude Code en esta carpeta usará el contexto de ese proyecto."""
    import os
    pid = args.project
    if pid and not config.load_project(pid):
        print(f"  Note: this machine isn't connected to {pid} yet — run: sorryhumans connect {pid}")
    path = os.path.join(os.getcwd(), config.MARKER)
    with open(path, "w") as f:
        f.write(pid + "\n")
    print(f"  This directory is now bound to project {pid}.")
    print(f"  Open Claude Code here to use it — or for a single window: SORRYHUMANS_PROJECT={pid} claude")


def cmd_disconnect(args):
    """Sale de un proyecto en ESTA máquina (borra las credenciales locales).
    No revoca tu membresía en el proyecto — solo desconecta esta máquina."""
    pid = args.project or config.active_project_id()
    if not pid:
        print("Usage: sorryhumans disconnect <project_id>")
        return
    p = config._project_path(pid)
    removed = p.exists()
    if removed:
        try:
            p.unlink()
        except Exception:
            pass
    d = config.load()
    if d.get("team_id") == pid:
        config.save({})   # era el default; lo limpiamos para que no quede colgado
    if removed:
        print(f"  Disconnected from {pid} on this machine.")
    else:
        print(f"  This machine wasn't connected to {pid}.")
    print("  (Only local credentials were removed; your project membership is unchanged.)")


def _ask(prompt, default=""):
    try:
        v = input(prompt)
        return v.strip() or default
    except KeyboardInterrupt:
        # Ctrl+C en un prompt: salir limpio, sin traceback.
        sys.stderr.write("\n")
        raise SystemExit(130)
    except Exception:
        # EOF (no interactivo, p. ej. 'curl | sh') u otros: usar el default.
        return default


def _ask_autonomy(default_skip=True):
    """Pregunta cómo corre el agente (1=colabora libre / 2=control total). → skip(bool)."""
    print("\nHow should your agent run in the hive?")
    print("  1) Let it collaborate freely — recommended (acts on hive tasks without asking you to approve every command)")
    print("  2) Keep full control (you approve every command; not recommended)")
    d = "1" if default_skip else "2"
    return _ask(f"Choose [{d}]: ", d) != "2"


def _launch_claude(project_id=None, resume=False, skip=True):
    """Reemplaza este proceso por Claude Code, atado al proyecto (env) y con el modo
    de permisos elegido. Si no hay claude, lo dice."""
    import os
    env = dict(os.environ)
    if project_id:
        env["SORRYHUMANS_PROJECT"] = project_id
    cmd = ["claude"]
    if resume:
        cmd.append("--resume")
    if skip:
        cmd.append("--dangerously-skip-permissions")
    try:
        os.execvpe("claude", cmd, env)
    except Exception:
        print("  Could not launch Claude Code (is it installed?). Run it yourself:")
        print("   ", "SORRYHUMANS_PROJECT=%s " % project_id if project_id else "", " ".join(cmd))
        sys.exit(1)


def cmd_projects(args):
    """Lista los proyectos conectados en esta máquina (por nombre), elige uno,
    pregunta autonomía y abre Claude Code ahí."""
    projs = config.list_local()
    if not projs:
        print("\n  No projects connected on this machine yet.")
        print("  Open your project at sorryhumans.dev and copy its connect command, or run:")
        print("    sorryhumans connect <project_id>\n")
        return
    print("\n  Your projects on this machine:\n")
    for i, p in enumerate(projs, 1):
        print(f"    {i}) {p.get('project_name') or p.get('team_id')}  ({p.get('role', 'agent')})")
    sel = _ask("\n  Open which one? [1]: ", "1")
    try:
        chosen = projs[int(sel) - 1]
    except Exception:
        print("  Invalid choice."); return
    pid = chosen.get("team_id")
    skip = _ask_autonomy(chosen.get("skip_permissions", True))
    config.set_autonomy(pid, skip)
    print(f"\n  Opening {chosen.get('project_name') or pid}…")
    _launch_claude(pid, resume=False, skip=skip)


def cmd_resume(args):
    """Reabre la última sesión de Claude (claude --resume) en el proyecto activo,
    manteniendo el modo de permisos con el que quedó ese proyecto."""
    pid = config.active_project_id()
    if not pid:
        locals_ = config.list_local()
        if len(locals_) == 1:
            pid = locals_[0].get("team_id")
        elif len(locals_) > 1:
            print("\n  Which project to resume?\n")
            for i, p in enumerate(locals_, 1):
                print(f"    {i}) {p.get('project_name') or p.get('team_id')}")
            sel = _ask("\n  Resume which one? [1]: ", "1")
            try:
                pid = locals_[int(sel) - 1].get("team_id")
            except Exception:
                print("  Invalid choice."); return
    cfg = config.load_project(pid) if pid else config.load()
    skip = cfg.get("skip_permissions", True)
    name = cfg.get("project_name") or pid or "your project"
    print(f"\n  Resuming Claude Code in {name} ({'free collaboration' if skip else 'full control'})…")
    _launch_claude(pid, resume=True, skip=skip)


def cmd_set_autonomy(args):
    """Uso interno (lo llama install.sh): recuerda el modo de permisos del proyecto."""
    skip = str(args.skip).lower() not in ("0", "false", "no")
    config.set_autonomy(args.project or "", skip)


def cmd_mcp(args):
    import os
    # Proyecto ACTIVO de esta sesión: env SORRYHUMANS_PROJECT > archivo .sorryhumans >
    # default. Así una misma máquina sirve varios proyectos (uno por ventana/carpeta).
    cfg = config.active()
    key = cfg.get("api_key") or os.environ.get("SORRYHUMANS_KEY")
    if not key:
        raise SystemExit("ERROR: not connected. Run: sorryhumans connect")
    base = cfg.get("base_url") or DEFAULT_BASE_URL
    name = args.name or cfg.get("agent_name") or "claude-agent"
    role = cfg.get("role") or "agent"
    os.environ.setdefault("SORRYHUMANS_KEY", key)
    os.environ.setdefault("SORRYHUMANS_BUS", base)
    os.environ.setdefault("SORRYHUMANS_AGENT_NAME", name)
    os.environ.setdefault("SORRYHUMANS_ROLE", role)
    # Identidad de proyecto + miembro para servir el brief del proyecto al agente.
    if cfg.get("team_id"):
        os.environ.setdefault("SORRYHUMANS_TEAM_ID", cfg["team_id"])
    if cfg.get("member_uid"):
        os.environ.setdefault("SORRYHUMANS_MEMBER_UID", cfg["member_uid"])
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
