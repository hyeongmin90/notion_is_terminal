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

        if block_is_usable_code(terminal) and block_is_usable_code(input_block):
            return RuntimeBlocks(
                terminal_block_id=terminal_block_id,
                input_block_id=input_block_id,
                recreated=False,
            )

        # Keep the UI unambiguous: when either runtime block is damaged, retire
        # whichever old runtime block remains and create a fresh matched pair.
        for block_id, block in (
            (terminal_block_id, terminal),
            (input_block_id, input_block),
        ):
            if block is not None and not block.get("archived") and not block.get("in_trash"):
                try:
                    self.archive_block(block_id)
                except NotionError:
                    pass

        created = self.append_runtime_blocks(
            page_id=page_id,
            terminal_text=terminal_text,
            input_text=input_text,
        )
        return RuntimeBlocks(
            terminal_block_id=created.terminal_block_id,
            input_block_id=created.input_block_id,
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
                code_block_payload(terminal_text, language="plain text"),
                heading_payload("Input"),
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
        paragraph_payload("Type after the prompt. Press Enter twice to submit normal input."),
        code_block_payload(input_text, language="bash"),
        divider_payload(),
        heading_payload("Controls"),
        bulleted_payload("Interrupt immediately: ^C"),
        bulleted_payload("EOF / suspend / clear / quit signal: ^D, ^Z, ^L, ^\\"),
        bulleted_payload("Special key: :key UP, :key DOWN, :key LEFT, :key RIGHT, :key ESC, :key TAB, :key F1 ... F12"),
        bulleted_payload(r"Raw keystrokes: :send \e:wq\r"),
        bulleted_payload("Resize terminal: :resize 140x50"),
        bulleted_payload("Normal prompts such as [Y/n] can be answered by typing y and pressing Enter twice."),
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
