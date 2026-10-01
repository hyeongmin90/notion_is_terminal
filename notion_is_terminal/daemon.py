from __future__ import annotations

import selectors
import time

from .config import AppConfig
from .notion import NotionClient, NotionError
from .protocol import InputAction, InputKind, extract_submission
from .terminal import PTYSession


class TerminalDaemon:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
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
            self._reset_input()
            self._write_terminal(force=True)

            now = time.monotonic()
            next_poll = now
            next_render = now

            while self.session.is_alive():
                now = time.monotonic()
                timeout = max(0.0, min(next_poll, next_render) - now)
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

            self.session.read_ready()
            self._dirty = True
            self._write_terminal(force=True, suffix="\n\n[notion_is_terminal: shell session ended]")
            self.notion.update_code_block(
                self.config.notion.input_block_id,
                "[SESSION ENDED] Restart `notion-terminal run` locally.",
                language="plain text",
            )
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
            print(f"[notion] terminal update failed: {exc}")
