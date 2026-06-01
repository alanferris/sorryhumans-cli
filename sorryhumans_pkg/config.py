"""Config management — stores api_key, agent_id, team_id locally."""
import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".sorryhumans" / "config.json"


def load() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


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
