from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


MAX_RICH_TEXT_CHUNK = 1900
MAX_RICH_TEXT_ITEMS = 100


class NotionError(RuntimeError):
    pass


@dataclass(slots=True)
class CreatedTerminalPage:
    page_id: str
    page_url: str
    terminal_block_id: str
    input_block_id: str


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
        if block.get("type") != "code":
            raise NotionError(f"Block {block_id} is not a code block.")
        return "".join(item.get("plain_text", "") for item in block.get("code", {}).get("rich_text", []))

    def update_code_block(self, block_id: str, text: str, *, language: str = "plain text") -> None:
        self._request("PATCH", f"/blocks/{block_id}", json={
            "code": {"rich_text": rich_text_payload(text), "language": language}
        })

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
            "children": [
                code_block_payload(terminal_text, language="plain text"),
                code_block_payload(input_text, language="bash"),
            ]
        })
        code_blocks = [item for item in children.get("results", []) if item.get("type") == "code"]
        if len(code_blocks) < 2:
            raise NotionError("Notion created the page, but the two terminal code blocks were not returned.")

        return CreatedTerminalPage(
            page_id=page_id,
            page_url=page.get("url", ""),
            terminal_block_id=code_blocks[0]["id"],
            input_block_id=code_blocks[1]["id"],
        )

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
            raise NotionError(f"Notion API {response.status_code}{suffix}: {message}")

        raise NotionError("Notion request failed after retries.")


def rich_text_payload(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    chunks = [text[i:i + MAX_RICH_TEXT_CHUNK] for i in range(0, len(text), MAX_RICH_TEXT_CHUNK)]
    if len(chunks) > MAX_RICH_TEXT_ITEMS:
        max_chars = MAX_RICH_TEXT_CHUNK * MAX_RICH_TEXT_ITEMS
        text = text[-max_chars:]
        chunks = [text[i:i + MAX_RICH_TEXT_CHUNK] for i in range(0, len(text), MAX_RICH_TEXT_CHUNK)]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def code_block_payload(text: str, *, language: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {"caption": [], "rich_text": rich_text_payload(text), "language": language},
    }


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
