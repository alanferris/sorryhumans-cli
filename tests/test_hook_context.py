"""Unit tests del hook SessionStart (`sorryhumans hook-context`).

El hook se instala en el settings GLOBAL de Claude Code, así que corre al arrancar
CUALQUIER sesión, en cualquier carpeta. Solo debe inyectar el brief + el mandato del
Monitor cuando ESTA sesión está atada explícitamente a un proyecto (env
SORRYHUMANS_PROJECT o marker .sorryhumans). Sin binding -> additionalContext vacío,
para no contaminar sesiones ajenas (p. ej. desarrollar el propio CLI).

No necesita backend: el branch de red se evita y solo validamos el gate.
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli, config


def _run_hook_context() -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.cmd_hook_context(None)
    return json.loads(buf.getvalue())


def test_no_binding_emits_empty(monkeypatch):
    """Sin proyecto activo (ni env ni marker) -> {} (sesión limpia, sin inyección)."""
    monkeypatch.setattr(config, "active_project_id", lambda: None)
    out = _run_hook_context()
    assert out == {}


def test_binding_emits_monitor_directive(monkeypatch):
    """Con proyecto activo -> inyecta el mandato del Monitor en additionalContext.

    Dejamos la config sin api_key/team para que el branch de red se salte (no hay bus
    en el test); igual debe emitirse el mandato del Monitor, que es lo no-negociable.
    """
    monkeypatch.setattr(config, "active_project_id", lambda: "t_test")
    monkeypatch.setattr(config, "active", lambda: {})  # sin key/team -> sin llamada de red
    out = _run_hook_context()
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "ARM a persistent Monitor" in ctx
    assert "sorryhumans listen --follow" in ctx
