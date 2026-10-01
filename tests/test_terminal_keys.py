from notion_is_terminal.config import TerminalSettings
from notion_is_terminal.terminal import PTYSession


def _sent_for(key: str) -> bytes:
    session = PTYSession(TerminalSettings())
    sent = []
    session.send_bytes = sent.append
    session.send_key(key)
    return sent[0]


def test_enter_aliases():
    assert _sent_for("ENTER") == b"\r"
    assert _sent_for("RET") == b"\r"
    assert _sent_for("ENT") == b"\r"


def test_backspace_aliases():
    assert _sent_for("BACKSPACE") == b"\x7f"
    assert _sent_for("BS") == b"\x7f"
    assert _sent_for("BKSP") == b"\x7f"


def test_navigation_aliases():
    assert _sent_for("DEL") == b"\x1b[3~"
    assert _sent_for("INS") == b"\x1b[2~"
    assert _sent_for("PGUP") == b"\x1b[5~"
    assert _sent_for("PGDN") == b"\x1b[6~"
