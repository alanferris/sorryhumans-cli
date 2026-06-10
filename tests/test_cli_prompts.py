"""UX tests for the CLI prompts:
  - Ctrl+C at a prompt exits cleanly (SystemExit 130), never a traceback.
  - EOF (non-interactive) uses the default.
  - A mistyped command offers the closest match + a selectable menu.
"""
import argparse
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli


def test_ask_ctrl_c_exits_clean():
    """Ctrl+C in input() -> SystemExit(130), without propagating KeyboardInterrupt."""
    with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
        try:
            cli._ask("prompt: ")
            assert False, "should have exited"
        except SystemExit as e:
            assert e.code == 130


def test_ask_eof_uses_default():
    """EOF (no interactivo, p. ej. 'curl | sh') -> default, no error."""
    with mock.patch("builtins.input", side_effect=EOFError):
        assert cli._ask("prompt: ", "fallback") == "fallback"


def _sub_with_commands():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command")
    sub.add_parser("hive", help="See who is awake")
    sub.add_parser("projects", help="List your projects and open one")
    sub.add_parser("resume", help="Resume your last Claude session")
    sub.add_parser("internal", add_help=False)  # no help -> must NOT appear in the menu
    return sub


def test_suggest_picks_by_number():
    sub = _sub_with_commands()
    with mock.patch.object(cli, "_ask", return_value="2"):
        assert cli._suggest_command(sub, "xyz") == "projects"


def test_suggest_accepts_command_name_typed():
    sub = _sub_with_commands()
    with mock.patch.object(cli, "_ask", return_value="resume"):
        assert cli._suggest_command(sub, "xyz") == "resume"


def test_suggest_empty_cancels():
    sub = _sub_with_commands()
    with mock.patch.object(cli, "_ask", return_value=""):
        assert cli._suggest_command(sub, "zzzz") is None


def test_suggest_did_you_mean_defaults_to_closest(capsys):
    """'projcts' ~ 'projects': suggested, and the prompt default points to that number."""
    sub = _sub_with_commands()
    captured = {}
    def fake_ask(prompt, default=""):
        captured["default"] = default
        return default
    with mock.patch.object(cli, "_ask", side_effect=fake_ask):
        chosen = cli._suggest_command(sub, "projcts")
    out = capsys.readouterr().out
    assert "Did you mean 'projects'?" in out
    assert "internal" not in out          # commands without help aren't listed
    assert chosen == "projects"           # Enter accepts the suggestion
    assert captured["default"] == "2"     # default = number of 'projects'
