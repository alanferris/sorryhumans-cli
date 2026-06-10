"""Unpredictable developer behavior: weird inputs, corrupt config, junk args.

Launch goal: no reasonable (or not-so-reasonable) use should throw a
traceback. Everything must degrade cleanly or guide the user.

Offline: no network. Tests that touch disk isolate in tmp_path.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli, config


# ── config corrupta / parcial ────────────────────────────────────────────────

def test_corrupt_config_json_degrades_to_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{ this is not json ]")
    assert config.load() == {}            # doesn't blow up, degrades to {}


def test_corrupt_project_json_degrades_to_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "t_x.json").write_text("nope")
    assert config.load_project("t_x") == {}


def test_empty_marker_file_is_ignored(monkeypatch, tmp_path):
    """An empty .sorryhumans must not select a phantom project."""
    monkeypatch.delenv("SORRYHUMANS_PROJECT", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    (work / config.MARKER).write_text("\n")
    monkeypatch.chdir(work)
    assert config.active_project_id() is None


# ── args basura a nivel main() ───────────────────────────────────────────────

def test_no_args_prints_help_and_exits(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["sorryhumans"])
    try:
        cli.main()
        assert False, "should have exited"
    except SystemExit as e:
        assert e.code == 1
    out = capsys.readouterr().out
    assert "summon" in out                # printed the help with the commands


def test_unknown_command_non_interactive_exits_clean(monkeypatch, capsys):
    """Nonexistent subcommand + cancel the menu -> exit 1, no traceback."""
    monkeypatch.setattr(sys, "argv", ["sorryhumans", "zzzz"])
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: "")   # Enter = cancelar
    try:
        cli.main()
        assert False
    except SystemExit as e:
        assert e.code == 1


def test_relay_bad_type_rejected_by_argparse(monkeypatch):
    """--type outside choices -> argparse exits 2 BEFORE running anything (no network)."""
    monkeypatch.setattr(sys, "argv", ["sorryhumans", "relay", "hi", "--type", "bogus"])
    try:
        cli.main()
        assert False
    except SystemExit as e:
        assert e.code == 2


# ── prompts hostiles ─────────────────────────────────────────────────────────

def test_ask_eof_returns_default():
    with mock.patch("builtins.input", side_effect=EOFError):
        assert cli._ask("? ", "fallback") == "fallback"


def test_ask_ctrl_c_exits_130():
    with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
        try:
            cli._ask("? ")
            assert False
        except SystemExit as e:
            assert e.code == 130
