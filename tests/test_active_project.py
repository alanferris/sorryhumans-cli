"""Tests for the ACTIVE project across per-session commands (multi-project).

Gap covered (G1, regression): listen/relay/hive/watch always read config.json
(the default project), so the Monitor could listen to the wrong project on a
machine with several projects. Now they resolve via config.active() (env > marker >
default) and the cursor is saved per-project, without crossing.

In single-project active()==default, so this is a no-op there (it still works).

Isolates everything in tmp_path: patches the config module paths and changes cwd, to
avoid touching this machine's real ~/.sorryhumans (which is connected live).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import config


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SH_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.delenv("SORRYHUMANS_PROJECT", raising=False)
    # clean cwd: make sure no .sorryhumans marker from a real parent leaks in.
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def test_env_project_selects_its_credentials(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key", "listen_cursor": "d"})
    config.save_project("t_b", {"api_key": "b_key", "listen_cursor": "b"})
    monkeypatch.setenv("SORRYHUMANS_PROJECT", "t_b")
    assert config.get_active("api_key") == "b_key"           # not the default
    assert config.require_active("api_key") == "b_key"


def test_dir_marker_selects_its_credentials(monkeypatch, tmp_path):
    work = _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key"})
    config.save_project("t_c", {"api_key": "c_key"})
    (work / config.MARKER).write_text("t_c\n")
    assert config.get_active("api_key") == "c_key"


def test_save_active_writes_to_active_project_only(monkeypatch, tmp_path):
    """Saving the active project's cursor must NOT clobber the default (no cross-bleed)."""
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key", "listen_cursor": "d0"})
    config.save_project("t_b", {"api_key": "b_key", "listen_cursor": "b0"})
    monkeypatch.setenv("SORRYHUMANS_PROJECT", "t_b")
    cfg = config.active()
    cfg["listen_cursor"] = "b1"
    config.save_active(cfg)
    assert config.load_project("t_b")["listen_cursor"] == "b1"   # B's advanced
    assert config.load()["listen_cursor"] == "d0"                # default intacto


def test_save_active_falls_back_to_default(monkeypatch, tmp_path):
    """With no active project, save_active writes the default config.json."""
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key"})
    cfg = config.active()
    cfg["listen_cursor"] = "x9"
    config.save_active(cfg)
    assert config.load()["listen_cursor"] == "x9"


def test_get_active_env_fallback_when_no_config(monkeypatch, tmp_path):
    """With no config files, get_active falls back to env (like the classic get())."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("SORRYHUMANS_KEY", "env_key")
    assert config.get_active("api_key", "SORRYHUMANS_KEY") == "env_key"


def test_require_active_missing_raises_with_guidance(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "only_key"})        # falta agent_id
    try:
        config.require_active("agent_id")
        assert False, "should have exited"
    except SystemExit as e:
        assert "connect" in str(e.code)
