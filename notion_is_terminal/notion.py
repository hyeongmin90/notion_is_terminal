from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


MAX_RICH_TEXT_CHUNK = 1900
MAX_RICH_TEXT_ITEMS = 100


class NotionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404 or self.code == "object_not_found"


@dataclass(slots=True)
class CreatedTerminalPage:
    page_id: str
    page_url: str
    terminal_block_id: str
    input_block_id: str


@dataclass(slots=True)
class RuntimeBlocks:
    terminal_block_id: str
    input_block_id: str
    recreated: bool = False


@dataclass(slots=True)
class RuntimeAnchors:
    terminal_anchor_id: str
    input_anchor_id: str


class NotionClient:
    def __init__(self, token: str, *, api_version: str = "2026-03-11", timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            base_url="https://api.notion.com/v1",
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
                "User-Agent": "notion-is-terminal/0.1",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NotionClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{page_id}")

    def get_block(self, block_id: str) -> dict[str, Any]:
        return self._request("GET", f"/blocks/{block_id}")

    def get_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            path = f"/blocks/{block_id}/children?page_size=100"
            if start_cursor:
                path += f"&start_cursor={start_cursor}"
            response = self._request("GET", path)
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                return results
            start_cursor = response.get("next_cursor")
            if not start_cursor:
                return results

    def get_code_text(self, block_id: str) -> str:
        block = self.get_block(block_id)
        if not block_is_usable_code(block):
            raise NotionError(f"Block {block_id} is not an active code block.")
        return "".join(item.get("plain_text", "") for item in block.get("code", {}).get("rich_text", []))

    def update_code_block(self, block_id: str, text: str, *, language: str = "plain text") -> None:
        self._request("PATCH", f"/blocks/{block_id}", json={
            "code": {"rich_text": rich_text_payload(text), "language": language}
        })

    def archive_block(self, block_id: str) -> None:
        self._request("PATCH", f"/blocks/{block_id}", json={"archived": True})

    def create_terminal_page(
        self,
        *,
        parent_page_id: str,
        title: str,
        terminal_text: str,
        input_text: str,
    ) -> CreatedTerminalPage:
        page = self._request("POST", "/pages", json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"type": "text", "text": {"content": title}}],
                }
            },
        })

        page_id = page["id"]
        children = self._request("PATCH", f"/blocks/{page_id}/children", json={
            "children": terminal_page_children(terminal_text, input_text)
        })
        terminal_id, input_id = _runtime_code_block_ids(children.get("results", []))

        return CreatedTerminalPage(
            page_id=page_id,
            page_url=page.get("url", ""),
            terminal_block_id=terminal_id,
            input_block_id=input_id,
        )

    def ensure_runtime_blocks(
        self,
        *,
        page_id: str,
        terminal_block_id: str,
        input_block_id: str,
        terminal_text: str,
        input_text: str,
    ) -> RuntimeBlocks:
        # The page is the durable anchor. If it is gone, silently creating a new
        # page elsewhere would be surprising, so page loss remains a hard error.
        self.get_page(page_id)

        terminal = self._try_get_block(terminal_block_id)
        input_block = self._try_get_block(input_block_id)
        children = self.get_block_children(page_id)
        anchors = find_runtime_anchors(children)

        both_usable = block_is_usable_code(terminal) and block_is_usable_code(input_block)
        in_place = bool(
            anchors
            and runtime_blocks_are_in_place(
                children,
                terminal_anchor_id=anchors.terminal_anchor_id,
                input_anchor_id=anchors.input_anchor_id,
                terminal_block_id=terminal_block_id,
                input_block_id=input_block_id,
            )
        )
        if both_usable and in_place:
            return RuntimeBlocks(
                terminal_block_id=terminal_block_id,
                input_block_id=input_block_id,
                recreated=False,
            )

        # Retire any surviving runtime blocks before recreating them. This also
        # migrates older self-healed pairs that were appended at the page end.
        for block_id, block in (
            (terminal_block_id, terminal),
            (input_block_id, input_block),
        ):
            if block is not None and not block.get("archived") and not block.get("in_trash"):
                try:
                    self.archive_block(block_id)
                except NotionError:
                    pass

        if anchors:
            return self.restore_runtime_blocks_at_anchors(
                page_id=page_id,
                anchors=anchors,
                terminal_text=terminal_text,
                input_text=input_text,
            )

        # Legacy/fallback path if a user also deleted or substantially changed
        # the stable headings/description blocks.
        return self.append_runtime_blocks(
            page_id=page_id,
            terminal_text=terminal_text,
            input_text=input_text,
        )

    def restore_runtime_blocks_at_anchors(
        self,
        *,
        page_id: str,
        anchors: RuntimeAnchors,
        terminal_text: str,
        input_text: str,
    ) -> RuntimeBlocks:
        terminal_response = self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={
                "children": [code_block_payload(terminal_text, language="plain text")],
                "position": {
                    "type": "after_block",
                    "after_block": {"id": anchors.terminal_anchor_id},
                },
            },
        )
        input_response = self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={
                "children": [code_block_payload(input_text, language="bash")],
                "position": {
                    "type": "after_block",
                    "after_block": {"id": anchors.input_anchor_id},
                },
            },
        )

        try:
            terminal_id = terminal_response["results"][0]["id"]
            input_id = input_response["results"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise NotionError("Notion did not return recreated runtime block IDs.") from exc

        return RuntimeBlocks(
            terminal_block_id=terminal_id,
            input_block_id=input_id,
            recreated=True,
        )

    def append_runtime_blocks(
        self,
        *,
        page_id: str,
        terminal_text: str,
        input_text: str,
    ) -> RuntimeBlocks:
        children = self._request("PATCH", f"/blocks/{page_id}/children", json={
            "children": [
                heading_payload("Terminal"),
                paragraph_payload("Live PTY screen. Do not edit this block manually."),
                code_block_payload(terminal_text, language="plain text"),
                heading_payload("Input"),
                paragraph_payload(
                    "Input uses a compact > prompt. Normal text is sent after Enter twice. "
                    "For TUI programs, use the key/control commands below when a real key press is required."
                ),
                code_block_payload(input_text, language="bash"),
                callout_payload("Runtime blocks were automatically recreated by notion_is_terminal.", "♻️"),
            ]
        })
        terminal_id, input_id = _runtime_code_block_ids(children.get("results", []))
        return RuntimeBlocks(
            terminal_block_id=terminal_id,
            input_block_id=input_id,
            recreated=True,
        )

    def _try_get_block(self, block_id: str) -> dict[str, Any] | None:
        try:
            return self.get_block(block_id)
        except NotionError as exc:
            if exc.is_not_found:
                return None
            raise

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        delay = 0.75
        for attempt in range(6):
            try:
                response = self._client.request(method, path, json=json)
            except httpx.HTTPError as exc:
                if attempt == 5:
                    raise NotionError(f"Notion request failed: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue

            if response.status_code < 400:
                return response.json()

            if response.status_code in {429, 503, 504, 529} and attempt < 5:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = max(float(retry_after), 0.25) if retry_after else delay
                except ValueError:
                    wait = delay
                time.sleep(wait)
                delay = min(delay * 2, 8.0)
                continue

            try:
                error = response.json()
                message = error.get("message") or response.text
                code = error.get("code")
            except ValueError:
                message = response.text
                code = None
            suffix = f" ({code})" if code else ""
            raise NotionError(
                f"Notion API {response.status_code}{suffix}: {message}",
                status_code=response.status_code,
                code=code,
            )

        raise NotionError("Notion request failed after retries.")


def block_is_usable_code(block: dict[str, Any] | None) -> bool:
    return bool(
        block
        and block.get("type") == "code"
        and not block.get("archived", False)
        and not block.get("in_trash", False)
    )


def block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not block_type:
        return ""
    content = block.get(block_type, {})
    return "".join(item.get("plain_text", "") for item in content.get("rich_text", []))


def find_runtime_anchors(children: list[dict[str, Any]]) -> RuntimeAnchors | None:
    terminal_anchor: str | None = None
    input_anchor: str | None = None
    section: str | None = None

    for block in children:
        if block.get("archived") or block.get("in_trash"):
            continue

        if block.get("type") == "heading_2":
            title = block_plain_text(block).strip()
            if title == "Terminal" and terminal_anchor is None:
                section = "terminal"
                continue
            if title == "Input" and input_anchor is None:
                section = "input"
                continue
            if section in {"terminal", "input"}:
                section = None

        if block.get("type") == "paragraph":
            if section == "terminal" and terminal_anchor is None:
                terminal_anchor = block.get("id")
                section = None
            elif section == "input" and input_anchor is None:
                input_anchor = block.get("id")
                section = None

        if terminal_anchor and input_anchor:
            return RuntimeAnchors(terminal_anchor, input_anchor)

    return None


def runtime_blocks_are_in_place(
    children: list[dict[str, Any]],
    *,
    terminal_anchor_id: str,
    input_anchor_id: str,
    terminal_block_id: str,
    input_block_id: str,
) -> bool:
    active = [
        block for block in children
        if not block.get("archived") and not block.get("in_trash")
    ]
    ids = [block.get("id") for block in active]

    try:
        terminal_anchor_index = ids.index(terminal_anchor_id)
        input_anchor_index = ids.index(input_anchor_id)
    except ValueError:
        return False

    terminal_ok = (
        terminal_anchor_index + 1 < len(ids)
        and ids[terminal_anchor_index + 1] == terminal_block_id
    )
    input_ok = (
        input_anchor_index + 1 < len(ids)
        and ids[input_anchor_index + 1] == input_block_id
    )
    return terminal_ok and input_ok


def terminal_page_children(terminal_text: str, input_text: str) -> list[dict[str, Any]]:
    return [
        callout_payload(
            "This page is a live remote terminal. Anything submitted in Input runs on the local Linux/WSL user running notion-terminal.",
            "⚠️",
        ),
        heading_payload("Terminal"),
        paragraph_payload("Live PTY screen. Do not edit this block manually."),
        code_block_payload(terminal_text, language="plain text"),
        heading_payload("Input"),
        paragraph_payload(
            "Input uses a compact > prompt. Normal text is sent after Enter twice. "
            "For TUI programs, use the key/control commands below when a real key press is required."
        ),
        code_block_payload(input_text, language="bash"),
        divider_payload(),
        heading_payload("Controls"),
        bulleted_payload("Normal input — type text after > and press Enter twice. Example: > pwd"),
        bulleted_payload("Key press — :key NAME or short :k NAME. Example: :k ENTER"),
        bulleted_payload("Ctrl key — :ctrl KEY or short :c KEY. Example: :c O for Ctrl-O"),
        bulleted_payload(r"Raw bytes/text — :send TEXT or short :s TEXT. Escapes: \e, \x1b, \n, \r, \t, \\"),
        bulleted_payload("Resize — :resize COLSxROWS or short :rs COLSxROWS. Example: :rs 140x50"),
        heading_payload("Key names and aliases"),
        bulleted_payload("ENTER aliases: ENTER, RETURN, RET, ENT"),
        bulleted_payload("BACKSPACE aliases: BACKSPACE, BS, BKSP"),
        bulleted_payload("ESC aliases: ESC, ESCAPE"),
        bulleted_payload("DELETE / INSERT aliases: DELETE/DEL, INSERT/INS"),
        bulleted_payload("PAGE keys: PAGEUP/PGUP, PAGEDOWN/PGDN"),
        bulleted_payload("Navigation: UP, DOWN, LEFT, RIGHT, HOME, END, TAB, F1 ... F12"),
        heading_payload("Immediate control tokens"),
        paragraph_payload(
            "^C, ^D, ^Z, ^L and ^\\ are recognized immediately without the extra blank-line submit. "
            "Use ^C to interrupt a running process, ^D for EOF, ^Z to suspend, and ^L to clear/redraw."
        ),
        heading_payload("Common TUI recipes"),
        bulleted_payload("Codex / Claude Code — type text normally; if it appears in the input box but does not submit, use :k ENTER separately."),
        bulleted_payload("Codex / editors — delete one character with :k BS; move with :k LEFT / :k RIGHT."),
        bulleted_payload("nano — save: :c O, confirm filename: :k ENTER, exit: :c X, search: :c W."),
        bulleted_payload(r"vim — raw sequence example to save and quit: :s \e:wq\r"),
        bulleted_payload("Prompts such as [Y/n] — type y, then Enter twice. If the program needs a literal key event, use :k ENTER."),
        callout_payload(
            "Do not enter sudo passwords, API keys, or other secrets in Notion. Use a local authentication step instead.",
            "🔐",
        ),
        paragraph_payload(
            "If either Terminal or Input code block is deleted or moved to trash, the daemon recreates a fresh matched pair and updates its local config automatically."
        ),
    ]


def rich_text_payload(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    chunks = [text[i:i + MAX_RICH_TEXT_CHUNK] for i in range(0, len(text), MAX_RICH_TEXT_CHUNK)]
    if len(chunks) > MAX_RICH_TEXT_ITEMS:
        max_chars = MAX_RICH_TEXT_CHUNK * MAX_RICH_TEXT_ITEMS
        text = text[-max_chars:]
        chunks = [text[i:i + MAX_RICH_TEXT_CHUNK] for i in range(0, len(text), MAX_RICH_TEXT_CHUNK)]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _simple_rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text}}]


def code_block_payload(text: str, *, language: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {"caption": [], "rich_text": rich_text_payload(text), "language": language},
    }


def heading_payload(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _simple_rich_text(text)},
    }


def paragraph_payload(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _simple_rich_text(text)},
    }


def bulleted_payload(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _simple_rich_text(text)},
    }


def callout_payload(text: str, emoji: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _simple_rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
        },
    }


def divider_payload() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _runtime_code_block_ids(results: list[dict[str, Any]]) -> tuple[str, str]:
    code_blocks = [item for item in results if item.get("type") == "code"]
    if len(code_blocks) < 2:
        raise NotionError("Notion did not return the two runtime code blocks.")
    return code_blocks[0]["id"], code_blocks[1]["id"]


def parse_page_id(value: str) -> str:
    compact = value.strip()
    uuid_match = re.fullmatch(
        r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}",
        compact,
    )
    if uuid_match:
        return _hyphenate_uuid(re.sub(r"-", "", compact))

    matches = re.findall(r"[0-9a-fA-F]{32}", compact)
    if not matches:
        raise ValueError("Could not find a Notion page ID in the provided value.")
    return _hyphenate_uuid(matches[-1])


def _hyphenate_uuid(value: str) -> str:
    raw = value.replace("-", "")
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
