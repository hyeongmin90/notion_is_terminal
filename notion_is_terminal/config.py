from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "notion_is_terminal" / "config.toml"


@dataclass(slots=True)
class NotionSettings:
    token: str
    page_id: str
    terminal_block_id: str
    input_block_id: str
    page_url: str = ""
    api_version: str = "2026-03-11"


@dataclass(slots=True)
class TerminalSettings:
    shell: str = "/bin/bash"
    cwd: str = str(Path.home())
    user: str = os.environ.get("USER", "user")
    host: str = "ubuntu"
    columns: int = 120
    rows: int = 40
    poll_interval: float = 1.2
    refresh_interval: float = 1.5
    health_check_interval: float = 10.0
    show_cursor: bool = True
    source_bashrc: bool = True


@dataclass(slots=True)
class AppConfig:
    notion: NotionSettings
    terminal: TerminalSettings


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    config_path = Path(path).expanduser()
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    notion_raw = raw.get("notion", {})
    terminal_raw = raw.get("terminal", {})

    token = os.environ.get("NOTION_TOKEN") or notion_raw.get("token", "")
    if not token:
        raise ValueError("Notion token is missing from config and NOTION_TOKEN is not set.")

    notion = NotionSettings(
        token=token,
        page_id=_required(notion_raw, "page_id"),
        terminal_block_id=_required(notion_raw, "terminal_block_id"),
        input_block_id=_required(notion_raw, "input_block_id"),
        page_url=notion_raw.get("page_url", ""),
        api_version=notion_raw.get("api_version", "2026-03-11"),
    )

    terminal = TerminalSettings(
        shell=terminal_raw.get("shell", "/bin/bash"),
        cwd=terminal_raw.get("cwd", str(Path.home())),
        user=terminal_raw.get("user", os.environ.get("USER", "user")),
        host=terminal_raw.get("host", "ubuntu"),
        columns=int(terminal_raw.get("columns", 120)),
        rows=int(terminal_raw.get("rows", 40)),
        poll_interval=float(terminal_raw.get("poll_interval", 1.2)),
        refresh_interval=float(terminal_raw.get("refresh_interval", 1.5)),
        health_check_interval=float(terminal_raw.get("health_check_interval", 10.0)),
        show_cursor=bool(terminal_raw.get("show_cursor", True)),
        source_bashrc=bool(terminal_raw.get("source_bashrc", True)),
    )

    _validate_terminal(terminal)
    return AppConfig(notion=notion, terminal=terminal)


def write_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> Path:
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    text = "
".join(
        [
            "[notion]",
            f'token = {_toml_string(config.notion.token)}',
            f'api_version = {_toml_string(config.notion.api_version)}',
            f'page_id = {_toml_string(config.notion.page_id)}',
            f'terminal_block_id = {_toml_string(config.notion.terminal_block_id)}',
            f'input_block_id = {_toml_string(config.notion.input_block_id)}',
            f'page_url = {_toml_string(config.notion.page_url)}',
            "",
            "[terminal]",
            f'shell = {_toml_string(config.terminal.shell)}',
            f'cwd = {_toml_string(config.terminal.cwd)}',
            f'user = {_toml_string(config.terminal.user)}',
            f'host = {_toml_string(config.terminal.host)}',
            f"columns = {config.terminal.columns}",
            f"rows = {config.terminal.rows}",
            f"poll_interval = {config.terminal.poll_interval}",
            f"refresh_interval = {config.terminal.refresh_interval}",
            f"health_check_interval = {config.terminal.health_check_interval}",
            f"show_cursor = {'true' if config.terminal.show_cursor else 'false'}",
            f"source_bashrc = {'true' if config.terminal.source_bashrc else 'false'}",
            "",
        ]
    )

    config_path.write_text(text, encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except OSError:
        pass
    return config_path


def _required(raw: dict, key: str) -> str:
    value = str(raw.get(key, "")).strip()
    if not value:
        raise ValueError(f"Missing required config value: {key}")
    return value


def _validate_terminal(settings: TerminalSettings) -> None:
    if settings.columns < 20 or settings.columns > 400:
        raise ValueError("terminal.columns must be between 20 and 400")
    if settings.rows < 5 or settings.rows > 200:
        raise ValueError("terminal.rows must be between 5 and 200")
    if settings.poll_interval < 0.5:
        raise ValueError("terminal.poll_interval must be >= 0.5 seconds")
    if settings.refresh_interval < 0.5:
        raise ValueError("terminal.refresh_interval must be >= 0.5 seconds")
    if settings.health_check_interval < 3.0:
        raise ValueError("terminal.health_check_interval must be >= 3.0 seconds")


def _toml_string(value: str) -> str:
    escaped = value.replace("\", "\\").replace('"', '\"').replace("
", "\n")
    return f'"{escaped}"'
