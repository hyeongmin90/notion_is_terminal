from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class InputKind(Enum):
    LINE = auto()
    RAW = auto()
    CONTROL = auto()
    KEY = auto()
    RESIZE = auto()
    BROWSER = auto()
    NONE = auto()


@dataclass(slots=True)
class InputAction:
    kind: InputKind
    value: str = ""
    columns: int | None = None
    rows: int | None = None


IMMEDIATE_CONTROLS = {
    "^C": "C",
    "^D": "D",
    "^Z": "Z",
    "^L": "L",
    "^\\": "\\",
}


def extract_submission(block_text: str, prompt: str) -> tuple[InputAction | None, bool]:
    """Parse the Input code block.

    Normal text is submitted when it ends in a newline (one Enter in the
    Notion UI). This prevents polling from executing partially typed commands.
    Ctrl tokens such as ^C are recognized immediately so a runaway command can
    be interrupted without the trailing newline.
    """
    if not block_text.startswith(prompt):
        return None, False

    body = block_text[len(prompt) :]
    stripped = body.strip()

    if stripped in IMMEDIATE_CONTROLS and body.rstrip("\r\n").strip() == stripped:
        return InputAction(InputKind.CONTROL, IMMEDIATE_CONTROLS[stripped]), True

    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        return None, False

    payload = normalized[:-1]
    if not payload.strip():
        return InputAction(InputKind.NONE), True

    command = payload.strip("\n")
    command_stripped = command.strip()

    parsed = _split_command(command_stripped)
    if parsed is not None:
        name, value = parsed

        if name in {":ctrl", ":c"}:
            return InputAction(InputKind.CONTROL, value), True

        if name in {":key", ":k"}:
            return InputAction(InputKind.KEY, value), True

        if name in {":send", ":s"}:
            return InputAction(InputKind.RAW, decode_escapes(value)), True

        if name in {":resize", ":rs"}:
            size = value.lower().replace("x", " ").split()
            if len(size) != 2:
                raise ValueError("Usage: :resize <columns>x<rows> or :rs <columns>x<rows>")
            columns, rows = int(size[0]), int(size[1])
            return InputAction(InputKind.RESIZE, columns=columns, rows=rows), True

        if name in {":browser", ":b"}:
            return InputAction(InputKind.BROWSER, value), True

    return InputAction(InputKind.LINE, command), True


def _split_command(value: str) -> tuple[str, str] | None:
    if not value.startswith(":"):
        return None
    parts = value.split(maxsplit=1)
    if len(parts) != 2:
        return None
    return parts[0].lower(), parts[1].strip()


def decode_escapes(value: str) -> str:
    """Decode common terminal escapes while preserving ordinary Unicode."""
    out: list[str] = []
    i = 0
    while i < len(value):
        if value[i] != "\\" or i + 1 >= len(value):
            out.append(value[i])
            i += 1
            continue
        nxt = value[i + 1]
        simple = {"n": "\n", "r": "\r", "t": "\t", "e": "\x1b", "\\": "\\"}
        if nxt in simple:
            out.append(simple[nxt])
            i += 2
            continue
        if nxt == "x" and i + 3 < len(value):
            hex_part = value[i + 2 : i + 4]
            try:
                out.append(chr(int(hex_part, 16)))
                i += 4
                continue
            except ValueError:
                pass
        out.append("\\")
        i += 1
    return "".join(out)
