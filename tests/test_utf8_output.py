"""El Monitor ('sorryhumans listen --follow') imprime un emoji 📬. En Windows la consola
es cp1252 y no puede codificarlo -> UnicodeEncodeError mata el proceso. Estos tests
reproducen ese fallo y verifican que reconfigurar a UTF-8 tolerante lo evita.
"""
import io
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli

EMOJI_LINE = "📬 hive: chat from agent@x — hola"


def _cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_emoji_crashes_on_cp1252_without_fix():
    """Reproduce el bug: escribir el emoji en un stream cp1252 estricto revienta."""
    s = _cp1252_stream()
    try:
        s.write(EMOJI_LINE)
        s.flush()
        assert False, "debería haber fallado en cp1252"
    except UnicodeEncodeError:
        pass


def test_reconfigure_makes_emoji_safe():
    """Tras _force_utf8_output, ese mismo stream ya no revienta con el emoji."""
    s = _cp1252_stream()
    with mock.patch.object(cli.sys, "stdout", s), mock.patch.object(cli.sys, "stderr", s):
        cli._force_utf8_output()
        # No debe lanzar:
        s.write(EMOJI_LINE)
        s.flush()
    assert s.encoding.lower().replace("-", "") == "utf8"


def test_force_utf8_never_raises_on_odd_streams():
    """Si el stream no soporta reconfigure (p. ej. ya envuelto/redirigido), no explota."""
    class NoReconfigure:
        def reconfigure(self, **kw):
            raise AttributeError("no reconfigure here")
    with mock.patch.object(cli.sys, "stdout", NoReconfigure()), \
         mock.patch.object(cli.sys, "stderr", NoReconfigure()):
        cli._force_utf8_output()  # no debe propagar


def test_main_skips_utf8_reconfigure_for_mcp(monkeypatch):
    """main() NO debe reconfigurar stdout para 'mcp' (rompería el stdio JSON-RPC)."""
    called = {"utf8": False}
    monkeypatch.setattr(cli, "_force_utf8_output", lambda: called.__setitem__("utf8", True))
    monkeypatch.setattr(cli, "cmd_mcp", lambda args: None)
    monkeypatch.setattr(cli.sys, "argv", ["sorryhumans", "mcp"])
    cli.main()
    assert called["utf8"] is False


def test_main_reconfigures_utf8_for_console_commands(monkeypatch):
    """Para comandos de consola (p. ej. hive) SÍ reconfigura."""
    called = {"utf8": False}
    monkeypatch.setattr(cli, "_force_utf8_output", lambda: called.__setitem__("utf8", True))
    monkeypatch.setattr(cli, "cmd_hive", lambda args: None)
    monkeypatch.setattr(cli.sys, "argv", ["sorryhumans", "hive"])
    cli.main()
    assert called["utf8"] is True
