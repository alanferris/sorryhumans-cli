"""El hook SessionStart debe apuntar al ejecutable REAL del venv con ruta completa.
En Windows, un comando 'sorryhumans' a secas resuelve a un binario sin extensión y
Claude Code dispara el diálogo "¿con qué app abrir esto?" al correr el hook.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli

WIN = os.path.expanduser("~/.sorryhumans/venv") + os.sep + os.path.join("Scripts", "sorryhumans.exe")
POSIX = os.path.expanduser("~/.sorryhumans/venv") + os.sep + os.path.join("bin", "sorryhumans")


def test_hook_command_windows_uses_exe_full_path():
    """Existe Scripts\\sorryhumans.exe -> ruta completa SIN comillas (PowerShell la ejecuta)."""
    with mock.patch("os.path.exists", lambda p: p.endswith(os.path.join("Scripts", "sorryhumans.exe"))):
        cmd = cli._hook_command()
    assert cmd.endswith("sorryhumans.exe hook-context")
    assert "Scripts" in cmd
    assert '"' not in cmd                   # SIN comillas: en PowerShell romperían el parseo


def test_hook_command_posix_uses_bin_full_path():
    with mock.patch("os.path.exists", lambda p: p.endswith(os.path.join("bin", "sorryhumans"))):
        cmd = cli._hook_command()
    assert cmd.endswith("sorryhumans hook-context")
    assert os.path.join("bin", "sorryhumans") in cmd or "/sorryhumans hook-context" in cmd
    assert '"' not in cmd


def test_hook_command_falls_back_when_no_venv():
    """Sin venv detectable: 'sorryhumans hook-context' (último recurso)."""
    with mock.patch("os.path.exists", lambda p: False):
        assert cli._hook_command() == "sorryhumans hook-context"
