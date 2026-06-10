"""_wire_session_hook must FIX an existing hook-context hook if its command differs
(e.g. an old Windows install with the path lacking .exe), not just skip it. Before,
it skipped whenever one existed, so a re-connect didn't repair old installs.
"""
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli

NEWCMD = "C:\\Users\\u\\.sorryhumans\\venv\\Scripts\\sorryhumans.exe hook-context"


def _settings(home):
    return os.path.join(home, ".claude", "settings.json")


def _write(home, data):
    os.makedirs(os.path.dirname(_settings(home)), exist_ok=True)
    with open(_settings(home), "w") as f:
        json.dump(data, f)


def _read(home):
    with open(_settings(home)) as f:
        return json.load(f)


def _hooks(data):
    return data["hooks"]["SessionStart"]


def test_corrects_stale_hook_command(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(str(tmp_path), {"hooks": {"SessionStart": [
        {"matcher": "startup", "hooks": [
            {"type": "command", "command": "sorryhumans hook-context", "timeout": 15}]}]}})
    with mock.patch.object(cli, "_hook_command", return_value=NEWCMD):
        cli._wire_session_hook()
    cmds = [h["command"] for e in _hooks(_read(str(tmp_path))) for h in e["hooks"]]
    assert NEWCMD in cmds
    assert "sorryhumans hook-context" not in cmds   # the old one was fixed, not duplicated


def test_installs_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(str(tmp_path), {})
    with mock.patch.object(cli, "_hook_command", return_value=NEWCMD):
        cli._wire_session_hook()
    cmds = [h["command"] for e in _hooks(_read(str(tmp_path))) for h in e["hooks"]]
    assert cmds == [NEWCMD]


def test_idempotent_when_already_correct(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(str(tmp_path), {"hooks": {"SessionStart": [
        {"matcher": "startup", "hooks": [
            {"type": "command", "command": NEWCMD, "timeout": 15}]}]}})
    with mock.patch.object(cli, "_hook_command", return_value=NEWCMD):
        cli._wire_session_hook()
    entries = _hooks(_read(str(tmp_path)))
    cmds = [h["command"] for e in entries for h in e["hooks"]]
    assert cmds == [NEWCMD]   # ni duplica ni rompe
