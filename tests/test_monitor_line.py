"""El preview del Monitor (listen --follow) trunca a 140 chars. Si el cuerpo es más largo,
debe marcarlo para que el agente lea el completo con check_messages en vez de actuar sobre
texto a medias (la fricción real que tuvimos coordinando con una máquina Windows).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli


def test_short_body_no_marker():
    line = cli._monitor_line({"type": "chat", "from_agent": "a_x", "body": "hola"})
    assert "hola" in line
    assert "check_messages" not in line


def test_long_body_marks_truncation():
    body = "x" * 200
    line = cli._monitor_line({"type": "task", "from_agent": "a_1", "body": body})
    assert "[+60 chars — usa check_messages]" in line   # 200 - 140 = 60
    assert line.count("x") == 140                         # solo 140 del cuerpo (a_1 no tiene 'x')


def test_missing_body_is_safe():
    line = cli._monitor_line({"type": "ack", "from_agent": "a_x"})
    assert "check_messages" not in line
    assert "a_x" in line
