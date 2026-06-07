"""Tests de UX de los prompts del CLI:
  - Ctrl+C en un prompt sale limpio (SystemExit 130), nunca traceback.
  - EOF (no interactivo) usa el default.
  - Un comando mal tecleado ofrece el más parecido + menú seleccionable.
"""
import argparse
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli


def test_ask_ctrl_c_exits_clean():
    """Ctrl+C en input() -> SystemExit(130), sin propagar KeyboardInterrupt."""
    with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
        try:
            cli._ask("prompt: ")
            assert False, "debió salir"
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
    sub.add_parser("internal", add_help=False)  # sin help -> NO debe aparecer en el menú
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
    """'projcts' ~ 'projects': se sugiere y el default del prompt apunta a ese número."""
    sub = _sub_with_commands()
    captured = {}
    def fake_ask(prompt, default=""):
        captured["default"] = default
        return default
    with mock.patch.object(cli, "_ask", side_effect=fake_ask):
        chosen = cli._suggest_command(sub, "projcts")
    out = capsys.readouterr().out
    assert "Did you mean 'projects'?" in out
    assert "internal" not in out          # los comandos sin help no se listan
    assert chosen == "projects"           # Enter acepta la sugerencia
    assert captured["default"] == "2"     # default = número de 'projects'
