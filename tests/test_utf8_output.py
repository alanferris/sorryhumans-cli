"""The Monitor ('sorryhumans listen --follow') prints a 📬 emoji. On Windows the console
is cp1252 and can't encode it -> UnicodeEncodeError kills the process. These tests
reproduce that failure and verify that reconfiguring to tolerant UTF-8 avoids it.
"""
import io
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorryhumans_pkg import cli

EMOJI_LINE = "📬 hive: chat from agent@x — hi"


def _cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_emoji_crashes_on_cp1252_without_fix():
    """Reproduce the bug: writing the emoji to a strict cp1252 stream blows up."""
    s = _cp1252_stream()
    try:
        s.write(EMOJI_LINE)
        s.flush()
        assert False, "should have failed on cp1252"
    except UnicodeEncodeError:
        pass


def test_reconfigure_makes_emoji_safe():
    """After _force_utf8_output, that same stream no longer blows up on the emoji."""
    s = _cp1252_stream()
    with mock.patch.object(cli.sys, "stdout", s), mock.patch.object(cli.sys, "stderr", s):
        cli._force_utf8_output()
        # Must not raise:
        s.write(EMOJI_LINE)
        s.flush()
    assert s.encoding.lower().replace("-", "") == "utf8"


def test_force_utf8_never_raises_on_odd_streams():
    """If the stream doesn't support reconfigure (e.g. already wrapped/redirected), it doesn't blow up."""
    class NoReconfigure:
        def reconfigure(self, **kw):
            raise AttributeError("no reconfigure here")
    with mock.patch.object(cli.sys, "stdout", NoReconfigure()), \
         mock.patch.object(cli.sys, "stderr", NoReconfigure()):
        cli._force_utf8_output()  # must not propagate


def test_main_skips_utf8_reconfigure_for_mcp(monkeypatch):
    """main() must NOT reconfigure stdout for 'mcp' (it would break the JSON-RPC stdio)."""
    called = {"utf8": False}
    monkeypatch.setattr(cli, "_force_utf8_output", lambda: called.__setitem__("utf8", True))
    monkeypatch.setattr(cli, "cmd_mcp", lambda args: None)
    monkeypatch.setattr(cli.sys, "argv", ["sorryhumans", "mcp"])
    cli.main()
    assert called["utf8"] is False


def test_main_reconfigures_utf8_for_console_commands(monkeypatch):
    """For console commands (e.g. hive) it DOES reconfigure."""
    called = {"utf8": False}
    monkeypatch.setattr(cli, "_force_utf8_output", lambda: called.__setitem__("utf8", True))
    monkeypatch.setattr(cli, "cmd_hive", lambda args: None)
    monkeypatch.setattr(cli.sys, "argv", ["sorryhumans", "hive"])
    cli.main()
    assert called["utf8"] is True
