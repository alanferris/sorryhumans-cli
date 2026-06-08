"""Tests del proyecto ACTIVO en los comandos por-sesión (multi-proyecto).

Gap que cubre (G1, regresión): listen/relay/hive/watch leían siempre config.json
(proyecto default), así que el Monitor podía escuchar el proyecto equivocado en una
máquina con varios proyectos. Ahora resuelven vía config.active() (env > marcador >
default) y el cursor se guarda por-proyecto, sin cruzarse.

En single-project active()==default, así que esto es no-op ahí (sigue funcionando).

Aísla todo en tmp_path: parchea los paths del módulo config y cambia de cwd, para no
tocar el ~/.sorryhumans real de esta máquina (que está conectada en vivo).
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
    # cwd limpio: que ningún marcador .sorryhumans de un padre real se cuele.
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def test_env_project_selects_its_credentials(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key", "listen_cursor": "d"})
    config.save_project("t_b", {"api_key": "b_key", "listen_cursor": "b"})
    monkeypatch.setenv("SORRYHUMANS_PROJECT", "t_b")
    assert config.get_active("api_key") == "b_key"           # no el default
    assert config.require_active("api_key") == "b_key"


def test_dir_marker_selects_its_credentials(monkeypatch, tmp_path):
    work = _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key"})
    config.save_project("t_c", {"api_key": "c_key"})
    (work / config.MARKER).write_text("t_c\n")
    assert config.get_active("api_key") == "c_key"


def test_save_active_writes_to_active_project_only(monkeypatch, tmp_path):
    """Guardar el cursor del proyecto activo NO debe pisar el default (sin cross-bleed)."""
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key", "listen_cursor": "d0"})
    config.save_project("t_b", {"api_key": "b_key", "listen_cursor": "b0"})
    monkeypatch.setenv("SORRYHUMANS_PROJECT", "t_b")
    cfg = config.active()
    cfg["listen_cursor"] = "b1"
    config.save_active(cfg)
    assert config.load_project("t_b")["listen_cursor"] == "b1"   # avanzó el de B
    assert config.load()["listen_cursor"] == "d0"                # default intacto


def test_save_active_falls_back_to_default(monkeypatch, tmp_path):
    """Sin proyecto activo, save_active escribe el config.json default."""
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "default_key"})
    cfg = config.active()
    cfg["listen_cursor"] = "x9"
    config.save_active(cfg)
    assert config.load()["listen_cursor"] == "x9"


def test_get_active_env_fallback_when_no_config(monkeypatch, tmp_path):
    """Sin archivos de config, get_active cae al env (como el get() clásico)."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("SORRYHUMANS_KEY", "env_key")
    assert config.get_active("api_key", "SORRYHUMANS_KEY") == "env_key"


def test_require_active_missing_raises_with_guidance(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.save({"api_key": "only_key"})        # falta agent_id
    try:
        config.require_active("agent_id")
        assert False, "debió salir"
    except SystemExit as e:
        assert "connect" in str(e.code)
