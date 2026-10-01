from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class InputKind(Enum):
    LINE = auto()
    RAW = auto()
    CONTROL = auto()
    KEY = auto()
    RESIZE = auto()
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

    Normal text is submitted only when it ends in a blank line (two newline
    characters). This prevents polling from executing partially typed commands.
    Ctrl tokens such as ^C are recognized immediately so a runaway command can
    be interrupted without the extra blank line.
    """
    if not block_text.startswith(prompt):
        return None, False

    body = block_text[len(prompt) :]
    stripped = body.strip()

    if stripped in IMMEDIATE_CONTROLS and body.rstrip("\r\n").strip() == stripped:
        return InputAction(InputKind.CONTROL, IMMEDIATE_CONTROLS[stripped]), True

    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n\n"):
        return None, False

    payload = normalized[:-2]
    if not payload.strip():
        return InputAction(InputKind.NONE), True

    command = payload.strip("\n")
    command_stripped = command.strip()

    if command_stripped.startswith(":ctrl "):
        return InputAction(InputKind.CONTROL, command_stripped[6:].strip()), True

    if command_stripped.startswith(":key "):
        return InputAction(InputKind.KEY, command_stripped[5:].strip()), True

    if command_stripped.startswith(":send "):
        raw = command_stripped[6:]
        return InputAction(InputKind.RAW, decode_escapes(raw)), True

    if command_stripped.startswith(":resize "):
        size = command_stripped[8:].strip().lower().replace("x", " ").split()
        if len(size) != 2:
            raise ValueError("Usage: :resize <columns> <rows>")
        columns, rows = int(size[0]), int(size[1])
        return InputAction(InputKind.RESIZE, columns=columns, rows=rows), True

    return InputAction(InputKind.LINE, command), True


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
