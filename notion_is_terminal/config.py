from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
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
    browser_status_block_id: str = ""
    browser_image_block_id: str = ""
    browser_vision_page_id: str = ""
    browser_vision_block_id: str = ""
    browser_vision_page_url: str = ""


@dataclass(slots=True)
class TerminalSettings:
    shell: str = "/bin/bash"
    cwd: str = str(Path.home())
    user: str = os.environ.get("USER", "user")
    host: str = "ubuntu"
    input_prompt: str = "> "
    columns: int = 120
    rows: int = 40
    poll_interval: float = 1.2
    refresh_interval: float = 1.5
    health_check_interval: float = 10.0
    show_cursor: bool = True
    source_bashrc: bool = True


@dataclass(slots=True)
class BrowserSettings:
    width: int = 1280
    height: int = 720
    headless: bool = True
    timeout_ms: int = 15000
    settle_ms: int = 350
    show_cursor_overlay: bool = True
    vision_enabled: bool = True
    vision_quality: int = 35
    vision_max_base64_chars: int = 160000


@dataclass(slots=True)
class AppConfig:
    notion: NotionSettings
    terminal: TerminalSettings
    browser: BrowserSettings = field(default_factory=BrowserSettings)


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    config_path = Path(path).expanduser()
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    notion_raw = raw.get("notion", {})
    terminal_raw = raw.get("terminal", {})
    browser_raw = raw.get("browser", {})

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
        browser_status_block_id=str(notion_raw.get("browser_status_block_id", "")),
        browser_image_block_id=str(notion_raw.get("browser_image_block_id", "")),
        browser_vision_page_id=str(notion_raw.get("browser_vision_page_id", "")),
        browser_vision_block_id=str(notion_raw.get("browser_vision_block_id", "")),
        browser_vision_page_url=str(notion_raw.get("browser_vision_page_url", "")),
    )

    terminal = TerminalSettings(
        shell=terminal_raw.get("shell", "/bin/bash"),
        cwd=terminal_raw.get("cwd", str(Path.home())),
        user=terminal_raw.get("user", os.environ.get("USER", "user")),
        host=terminal_raw.get("host", "ubuntu"),
        input_prompt=str(terminal_raw.get("input_prompt", "> ")),
        columns=int(terminal_raw.get("columns", 120)),
        rows=int(terminal_raw.get("rows", 40)),
        poll_interval=float(terminal_raw.get("poll_interval", 1.2)),
        refresh_interval=float(terminal_raw.get("refresh_interval", 1.5)),
        health_check_interval=float(terminal_raw.get("health_check_interval", 10.0)),
        show_cursor=bool(terminal_raw.get("show_cursor", True)),
        source_bashrc=bool(terminal_raw.get("source_bashrc", True)),
    )

    browser = BrowserSettings(
        width=int(browser_raw.get("width", 1280)),
        height=int(browser_raw.get("height", 720)),
        headless=bool(browser_raw.get("headless", True)),
        timeout_ms=int(browser_raw.get("timeout_ms", 15000)),
        settle_ms=int(browser_raw.get("settle_ms", 350)),
        show_cursor_overlay=bool(browser_raw.get("show_cursor_overlay", True)),
        vision_enabled=bool(browser_raw.get("vision_enabled", True)),
        vision_quality=int(browser_raw.get("vision_quality", 35)),
        vision_max_base64_chars=int(browser_raw.get("vision_max_base64_chars", 160000)),
    )

    _validate_terminal(terminal)
    _validate_browser(browser)
    return AppConfig(notion=notion, terminal=terminal, browser=browser)


def write_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> Path:
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    text = "\n".join(
        [
            "[notion]",
            f"token = {_toml_string(config.notion.token)}",
            f"api_version = {_toml_string(config.notion.api_version)}",
            f"page_id = {_toml_string(config.notion.page_id)}",
            f"terminal_block_id = {_toml_string(config.notion.terminal_block_id)}",
            f"input_block_id = {_toml_string(config.notion.input_block_id)}",
            f"page_url = {_toml_string(config.notion.page_url)}",
            f"browser_status_block_id = {_toml_string(config.notion.browser_status_block_id)}",
            f"browser_image_block_id = {_toml_string(config.notion.browser_image_block_id)}",
            f"browser_vision_page_id = {_toml_string(config.notion.browser_vision_page_id)}",
            f"browser_vision_block_id = {_toml_string(config.notion.browser_vision_block_id)}",
            f"browser_vision_page_url = {_toml_string(config.notion.browser_vision_page_url)}",
            "",
            "[terminal]",
            f"shell = {_toml_string(config.terminal.shell)}",
            f"cwd = {_toml_string(config.terminal.cwd)}",
            f"user = {_toml_string(config.terminal.user)}",
            f"host = {_toml_string(config.terminal.host)}",
            f"input_prompt = {_toml_string(config.terminal.input_prompt)}",
            f"columns = {config.terminal.columns}",
            f"rows = {config.terminal.rows}",
            f"poll_interval = {config.terminal.poll_interval}",
            f"refresh_interval = {config.terminal.refresh_interval}",
            f"health_check_interval = {config.terminal.health_check_interval}",
            f"show_cursor = {'true' if config.terminal.show_cursor else 'false'}",
            f"source_bashrc = {'true' if config.terminal.source_bashrc else 'false'}",
            "",
            "[browser]",
            f"width = {config.browser.width}",
            f"height = {config.browser.height}",
            f"headless = {'true' if config.browser.headless else 'false'}",
            f"timeout_ms = {config.browser.timeout_ms}",
            f"settle_ms = {config.browser.settle_ms}",
            f"show_cursor_overlay = {'true' if config.browser.show_cursor_overlay else 'false'}",
            f"vision_enabled = {'true' if config.browser.vision_enabled else 'false'}",
            f"vision_quality = {config.browser.vision_quality}",
            f"vision_max_base64_chars = {config.browser.vision_max_base64_chars}",
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
    if not settings.input_prompt:
        raise ValueError("terminal.input_prompt must not be empty")
    if "\n" in settings.input_prompt or "\r" in settings.input_prompt:
        raise ValueError("terminal.input_prompt must be a single line")
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


def _validate_browser(settings: BrowserSettings) -> None:
    if settings.width < 320 or settings.width > 3840:
        raise ValueError("browser.width must be between 320 and 3840")
    if settings.height < 240 or settings.height > 2160:
        raise ValueError("browser.height must be between 240 and 2160")
    if settings.timeout_ms < 1000:
        raise ValueError("browser.timeout_ms must be >= 1000")
    if settings.settle_ms < 0 or settings.settle_ms > 10000:
        raise ValueError("browser.settle_ms must be between 0 and 10000")
    if settings.vision_quality < 1 or settings.vision_quality > 100:
        raise ValueError("browser.vision_quality must be between 1 and 100")
    if settings.vision_max_base64_chars < 10000 or settings.vision_max_base64_chars > 180000:
        raise ValueError("browser.vision_max_base64_chars must be between 10000 and 180000")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
