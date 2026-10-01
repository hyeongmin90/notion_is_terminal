from __future__ import annotations

import getpass
import os
import shutil
from pathlib import Path

from .config import AppConfig, BrowserSettings, DEFAULT_CONFIG_PATH, NotionSettings, TerminalSettings, write_config
from .notion import NotionClient, parse_page_id


def run_init(config_path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    print("notion_is_terminal setup")
    print(
        "Creates one Notion page with a persistent terminal plus a Playwright "
        "browser observation surface for GPT.\n"
    )

    token = getpass.getpass("Notion integration token: ").strip()
    if not token:
        raise ValueError("Notion integration token is required.")

    parent_page_id = parse_page_id(input("Parent Notion page URL or page ID: ").strip())
    shell = _prompt("Shell", shutil.which("bash") or "/bin/bash")
    cwd = str(Path(_prompt("Initial working directory", str(Path.home()))).expanduser().resolve())
    user = _prompt("Prompt user", os.environ.get("USER", "user"))
    host = _prompt("Prompt host", "ubuntu")
    columns = int(_prompt("Terminal columns", "120"))
    rows = int(_prompt("Terminal rows", "40"))
    poll_interval = float(_prompt("Input poll interval (seconds)", "1.2"))
    refresh_interval = float(_prompt("Screen refresh interval (seconds)", "1.5"))
    title = _prompt("Notion page title", "Notion Terminal")

    terminal = TerminalSettings(
        shell=shell,
        cwd=cwd,
        user=user,
        host=host,
        input_prompt="> ",
        columns=columns,
        rows=rows,
        poll_interval=poll_interval,
        refresh_interval=refresh_interval,
        health_check_interval=10.0,
        show_cursor=True,
        source_bashrc=True,
    )

    browser = BrowserSettings()

    print("\nChecking Notion access and creating page...")
    with NotionClient(token) as notion:
        notion.get_page(parent_page_id)
        created = notion.create_terminal_page(
            parent_page_id=parent_page_id,
            title=title,
            terminal_text="notion_is_terminal\n\nLocal PTY is not connected yet. Run: notion-terminal run",
            input_text=terminal.input_prompt,
        )
        vision_page = notion.ensure_browser_vision_page(
            parent_page_id=created.page_id,
            page_id="",
            block_id="",
            idle_text=(
                "status: idle\n"
                "mime: image/jpeg\n"
                "encoding: base64\n"
                "data_base64:\n"
            ),
        )
        browser_blocks = notion.ensure_browser_blocks(
            page_id=created.page_id,
            status_block_id="",
            image_block_id="",
            status_text=(
                "status: idle\n"
                "browser: not started\n"
                f"viewport: {browser.width}x{browser.height}\n"
                f"vision_page_url: {vision_page.page_url}\n"
                "hint: :b goto <url> or :b shot\n"
            ),
        )

    config = AppConfig(
        notion=NotionSettings(
            token=token,
            page_id=created.page_id,
            terminal_block_id=created.terminal_block_id,
            input_block_id=created.input_block_id,
            page_url=created.page_url,
            browser_status_block_id=browser_blocks.status_block_id,
            browser_image_block_id=browser_blocks.image_block_id,
            browser_vision_page_id=vision_page.page_id,
            browser_vision_block_id=vision_page.block_id,
            browser_vision_page_url=vision_page.page_url,
        ),
        terminal=terminal,
        browser=browser,
    )
    written = write_config(config, config_path)

    print("\n✓ Notion connection verified")
    print("✓ Terminal page and built-in controls guide created")
    print("✓ Terminal code block created")
    print("✓ Input code block created with compact '> ' prompt")
    print("✓ Browser Status / Browser Screenshot surface created")
    print("✓ Browser Vision Payload child page created")
    print("✓ Runtime block self-healing enabled (10 second health check)")
    print(f"✓ Config written: {written}")
    if created.page_url:
        print(f"\nPage: {created.page_url}")
    print("\nStart in background with:\n  notion-terminal daemon start\n\nOr run in foreground with:\n  notion-terminal run")
    print("\nThe generated Notion page contains the input/control reference.")
    return config


def _prompt(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default
