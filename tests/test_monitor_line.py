"""El Monitor (listen --follow) NO debe cortar mensajes entre agentes: emite el body
COMPLETO (sin truncar), colapsando saltos de línea a espacios para que sea un solo evento.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli


def test_short_body_full():
    line = cli._monitor_line({"type": "chat", "from_agent": "a_x", "body": "hola"})
    assert line == "📬 hive: chat from a_x — hola"


def test_long_body_not_truncated():
    body = "x" * 500
    line = cli._monitor_line({"type": "task", "from_agent": "a_1", "body": body})
    assert ("x" * 500) in line          # completo, sin cortar
    assert "check_messages" not in line  # sin marcador de truncado
    assert "…" not in line


def test_newlines_collapsed_to_spaces():
    line = cli._monitor_line({"type": "result", "from_agent": "a_1", "body": "uno\ndos\n\ntres"})
    assert line == "📬 hive: result from a_1 — uno dos tres"


def test_missing_body_is_safe():
    line = cli._monitor_line({"type": "ack", "from_agent": "a_x"})
    assert line == "📬 hive: ack from a_x — "


def test_name_resolved_when_map_has_sender():
    line = cli._monitor_line({"type": "task", "from_agent": "a_xyz", "body": "hi"},
                             names={"a_xyz": "agent@box"})
    assert "agent@box" in line and "a_xyz" not in line


def test_unnamed_agent_falls_back_to_id_not_none():
    """Mapa con id->None (agente sin nombre): se muestra el id, nunca 'None'."""
    line = cli._monitor_line({"type": "chat", "from_agent": "a_xyz", "body": "hi"},
                             names={"a_xyz": None})
    assert "a_xyz" in line and "None" not in line
