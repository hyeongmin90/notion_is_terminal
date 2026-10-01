from __future__ import annotations

import selectors
import signal
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
        self._stop_requested = False

    @property
    def input_prompt(self) -> str:
        return self.config.terminal.input_prompt

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda _signum, _frame: self.request_stop())
        try:
            self.session.start()
            self.selector.register(self.session.fileno(), selectors.EVENT_READ)

            self._health_check()
            self._reset_input()
            self._write_terminal(force=True)

            now = time.monotonic()
            next_poll = now
            next_render = now
            next_health = now + self.config.terminal.health_check_interval

            while self.session.is_alive() and not self._stop_requested:
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

            if self.session.is_alive():
                self.session.send_control("C")
                time.sleep(0.05)
                self.session.close()
            else:
                self.session.read_ready()

            if self._stop_requested:
                try:
                    self.notion.update_code_block(
                        self.config.notion.input_block_id,
                        "[DAEMON STOPPED] Start with: notion-terminal daemon start",
                        language="plain text",
                    )
                except NotionError:
                    pass
            else:
                self._dirty = True
                self._write_terminal(force=True, suffix="\n\n[notion_is_terminal: shell session ended]")
                try:
                    self.notion.update_code_block(
                        self.config.notion.input_block_id,
                        "[SESSION ENDED] Restart with: notion-terminal run",
                        language="plain text",
                    )
                except NotionError:
                    pass
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
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
        self._set_input(self.input_prompt)

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
        input_text = self.input_prompt
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

        print("[notion] one or more runtime blocks were missing, invalid, or misplaced.")
        print("[notion] repaired only the affected runtime block(s) and updated config.toml.")
