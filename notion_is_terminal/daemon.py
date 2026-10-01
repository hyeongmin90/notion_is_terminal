from __future__ import annotations

import selectors
import time
from pathlib import Path

from .config import AppConfig, DEFAULT_CONFIG_PATH, write_config
from .notion import NotionClient, NotionError
from .protocol import InputAction, InputKind, extract_submission
from .terminal import PTYSession


class TerminalDaemon:
    def __init__(
        self,
        config: AppConfig,
        *,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path).expanduser()
        self.notion = NotionClient(config.notion.token, api_version=config.notion.api_version)
        self.session = PTYSession(config.terminal)
        self.selector = selectors.DefaultSelector()
        self._last_input_written = ""
        self._last_terminal_written = ""
        self._dirty = True

    def run(self) -> None:
        try:
            self.session.start()
            self.selector.register(self.session.fileno(), selectors.EVENT_READ)

            # Validate the configured block IDs before the first write. If a
            # user deleted one of them while the daemon was offline, recover
            # automatically and persist the new IDs.
            self._health_check()
            self._reset_input()
            self._write_terminal(force=True)

            now = time.monotonic()
            next_poll = now
            next_render = now
            next_health = now + self.config.terminal.health_check_interval

            while self.session.is_alive():
                now = time.monotonic()
                next_due = min(next_poll, next_render, next_health)
                timeout = max(0.0, next_due - now)
                events = self.selector.select(timeout=min(timeout, 0.25))
                if events and self.session.read_ready():
                    self._dirty = True

                now = time.monotonic()
                if now >= next_poll:
                    self._poll_input()
                    next_poll = now + self.config.terminal.poll_interval

                if now >= next_render:
                    self._write_terminal()
                    next_render = now + self.config.terminal.refresh_interval

                if now >= next_health:
                    self._health_check()
                    next_health = now + self.config.terminal.health_check_interval

            self.session.read_ready()
            self._dirty = True
            self._write_terminal(force=True, suffix="\n\n[notion_is_terminal: shell session ended]")
            try:
                self.notion.update_code_block(
                    self.config.notion.input_block_id,
                    "[SESSION ENDED] Restart `notion-terminal run` locally.",
                    language="plain text",
                )
            except NotionError:
                pass
        finally:
            try:
                self.selector.close()
            finally:
                self.session.close()
                self.notion.close()

    def _poll_input(self) -> None:
        try:
            text = self.notion.get_code_text(self.config.notion.input_block_id)
        except NotionError as exc:
            if exc.is_not_found:
                self._recover_runtime_blocks()
                return
            print(f"[notion] input poll failed: {exc}")
            return

        current_prompt = self.session.prompt()
        if text == self._last_input_written and current_prompt != self._last_input_written:
            self._set_input(current_prompt)
            return

        action, should_reset = extract_submission(text, self._last_input_written)
        if action is None:
            return

        try:
            self._dispatch(action)
        except Exception as exc:
            print(f"[input] {exc}")
            self._dirty = True
        finally:
            if should_reset:
                self._reset_input()

    def _dispatch(self, action: InputAction) -> None:
        if action.kind is InputKind.NONE:
            return
        if action.kind is InputKind.LINE:
            self.session.send_line(action.value)
            return
        if action.kind is InputKind.RAW:
            self.session.send_text(action.value)
            return
        if action.kind is InputKind.CONTROL:
            self.session.send_control(action.value)
            return
        if action.kind is InputKind.KEY:
            self.session.send_key(action.value)
            return
        if action.kind is InputKind.RESIZE:
            assert action.columns is not None and action.rows is not None
            self.session.resize(action.columns, action.rows)
            self._dirty = True
            return
        raise ValueError(f"Unhandled input action: {action.kind}")

    def _reset_input(self) -> None:
        self._set_input(self.session.prompt())

    def _set_input(self, text: str) -> None:
        try:
            self.notion.update_code_block(
                self.config.notion.input_block_id,
                text,
                language="bash",
            )
            self._last_input_written = text
        except NotionError as exc:
            if exc.is_not_found:
                self._recover_runtime_blocks()
                return
            print(f"[notion] input update failed: {exc}")

    def _write_terminal(self, *, force: bool = False, suffix: str = "") -> None:
        if not force and not self._dirty:
            return
        text = self.session.render() + suffix
        if not force and text == self._last_terminal_written:
            self._dirty = False
            return
        try:
            self.notion.update_code_block(
                self.config.notion.terminal_block_id,
                text,
                language="plain text",
            )
            self._last_terminal_written = text
            self._dirty = False
        except NotionError as exc:
            if exc.is_not_found:
                self._recover_runtime_blocks()
                return
            print(f"[notion] terminal update failed: {exc}")

    def _health_check(self) -> None:
        try:
            self._ensure_runtime_blocks()
        except NotionError as exc:
            if exc.is_not_found:
                raise RuntimeError(
                    "The configured Notion terminal page no longer exists or is not accessible. "
                    "Run `notion-terminal init` again if the page was deleted."
                ) from exc
            print(f"[notion] runtime block health check failed: {exc}")

    def _recover_runtime_blocks(self) -> None:
        try:
            self._ensure_runtime_blocks()
        except NotionError as exc:
            if exc.is_not_found:
                raise RuntimeError(
                    "The configured Notion terminal page no longer exists or is not accessible. "
                    "Run `notion-terminal init` again if the page was deleted."
                ) from exc
            print(f"[notion] runtime block recovery failed: {exc}")

    def _ensure_runtime_blocks(self) -> None:
        terminal_text = self.session.render()
        input_text = self.session.prompt()
        blocks = self.notion.ensure_runtime_blocks(
            page_id=self.config.notion.page_id,
            terminal_block_id=self.config.notion.terminal_block_id,
            input_block_id=self.config.notion.input_block_id,
            terminal_text=terminal_text,
            input_text=input_text,
        )
        if not blocks.recreated:
            return

        self.config.notion.terminal_block_id = blocks.terminal_block_id
        self.config.notion.input_block_id = blocks.input_block_id
        write_config(self.config, self.config_path)

        self._last_terminal_written = terminal_text
        self._last_input_written = input_text
        self._dirty = False

        print("[notion] runtime blocks were missing or invalid.")
        print("[notion] created a fresh Terminal/Input pair and updated config.toml.")
