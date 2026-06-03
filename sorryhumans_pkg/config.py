"""Config management.

Two layers:
  - config.json            : the default/last connection (back-compat).
  - projects/<team_id>.json : per-project credentials, so one machine can belong to
                              several projects at once.

The ACTIVE project for a given session is resolved by, in order:
  1. env SORRYHUMANS_PROJECT=<id>   (per terminal/window — even in the same directory)
  2. a `.sorryhumans` file in the cwd or any parent  (per directory)
  3. the default config.json        (last `connect`)
"""
import json
import os
from pathlib import Path

SH_DIR = Path.home() / ".sorryhumans"
CONFIG_PATH = SH_DIR / "config.json"
PROJECTS_DIR = SH_DIR / "projects"
MARKER = ".sorryhumans"   # per-directory project marker (a file holding a project id)


def load() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


# --- per-project storage ---------------------------------------------------
def _project_path(team_id: str) -> Path:
    return PROJECTS_DIR / f"{team_id}.json"


def save_project(team_id: str, data: dict) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    _project_path(team_id).write_text(json.dumps(data, indent=2))


def load_project(team_id: str) -> dict:
    p = _project_path(team_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _dir_project() -> str | None:
    """Walk cwd upward looking for a `.sorryhumans` FILE naming a project id."""
    try:
        cur = Path.cwd()
    except Exception:
        return None
    home = Path.home()
    while True:
        f = cur / MARKER
        if f.is_file():
            try:
                pid = f.read_text().strip().splitlines()[0].strip()
                if pid:
                    return pid
            except Exception:
                pass
        if cur == cur.parent or cur == home:
            break
        cur = cur.parent
    return None


def active_project_id() -> str | None:
    """Which project this session is bound to (env > directory marker > none)."""
    pid = os.environ.get("SORRYHUMANS_PROJECT")
    if pid and pid.strip():
        return pid.strip()
    return _dir_project()


def active() -> dict:
    """Config for the active project, falling back to the default config.json."""
    pid = active_project_id()
    if pid:
        c = load_project(pid)
        if c:
            return c
    return load()


def get(key: str, env_fallback: str = None):
    value = load().get(key)
    if value is None and env_fallback:
        value = os.environ.get(env_fallback)
    return value


def require(key: str, env_fallback: str = None):
    value = get(key, env_fallback)
    if not value:
        raise SystemExit(
            f"ERROR: '{key}' not configured. Run: sorryhumans connect"
        )
    return value
