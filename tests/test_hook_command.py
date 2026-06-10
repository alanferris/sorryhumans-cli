"""The SessionStart hook must point to the venv's REAL executable with a full path.
On Windows, a bare 'sorryhumans' command resolves to a binary without extension and
Claude Code pops the "which app should open this?" dialog when running the hook.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli

WIN = os.path.expanduser("~/.sorryhumans/venv") + os.sep + os.path.join("Scripts", "sorryhumans.exe")
POSIX = os.path.expanduser("~/.sorryhumans/venv") + os.sep + os.path.join("bin", "sorryhumans")


def test_hook_command_windows_uses_exe_full_path():
    """Scripts\\sorryhumans.exe exists -> full path with NO quotes (PowerShell runs it)."""
    with mock.patch("os.path.exists", lambda p: p.endswith(os.path.join("Scripts", "sorryhumans.exe"))):
        cmd = cli._hook_command()
    assert cmd.endswith("sorryhumans.exe hook-context")
    assert "Scripts" in cmd
    assert '"' not in cmd                   # NO quotes: in PowerShell they'd break parsing


def test_hook_command_posix_uses_bin_full_path():
    with mock.patch("os.path.exists", lambda p: p.endswith(os.path.join("bin", "sorryhumans"))):
        cmd = cli._hook_command()
    assert cmd.endswith("sorryhumans hook-context")
    assert os.path.join("bin", "sorryhumans") in cmd or "/sorryhumans hook-context" in cmd
    assert '"' not in cmd


def test_hook_command_falls_back_when_no_venv():
    """No detectable venv: 'sorryhumans hook-context' (last resort)."""
    with mock.patch("os.path.exists", lambda p: False):
        assert cli._hook_command() == "sorryhumans hook-context"


def test_hook_command_windows_uses_forward_slashes(monkeypatch):
    """Simulate Windows (backslash paths) -> the command comes out with '/' and no quotes,
    so it breaks neither in bash (\\ escaping) nor PowerShell (quotes)."""
    import ntpath
    monkeypatch.setattr("os.path.expanduser", lambda p: "C:\\Users\\elian\\.sorryhumans\\venv")
    monkeypatch.setattr("os.path.join", ntpath.join)
    monkeypatch.setattr("os.path.exists", lambda p: p.endswith("sorryhumans.exe"))
    cmd = cli._hook_command()
    assert cmd == "C:/Users/elian/.sorryhumans/venv/Scripts/sorryhumans.exe hook-context"
    assert "\\" not in cmd and '"' not in cmd
