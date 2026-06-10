"""Unit tests for the SessionStart hook (`sorryhumans hook-context`).

The hook is installed in Claude Code's GLOBAL settings, so it runs at the start of
ANY session, in any folder. It should only inject the brief + the Monitor mandate
when THIS session is explicitly bound to a project (env
SORRYHUMANS_PROJECT or a .sorryhumans marker). Without a binding -> empty additionalContext,
so it doesn't contaminate unrelated sessions (e.g. developing the CLI itself).

No backend needed: the network branch is skipped and we only validate the gate.
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
    """No active project (neither env nor marker) -> {} (clean session, no injection)."""
    monkeypatch.setattr(config, "active_project_id", lambda: None)
    out = _run_hook_context()
    assert out == {}


def test_binding_emits_monitor_directive(monkeypatch):
    """With an active project -> injects the Monitor mandate into additionalContext.

    We leave the config without api_key/team so the network branch is skipped (no bus
    in the test); the Monitor mandate must still be emitted, which is non-negotiable.
    """
    monkeypatch.setattr(config, "active_project_id", lambda: "t_test")
    monkeypatch.setattr(config, "active", lambda: {})  # no key/team -> no network call
    out = _run_hook_context()
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "ARM a persistent Monitor" in ctx
    assert "sorryhumans listen --follow" in ctx
