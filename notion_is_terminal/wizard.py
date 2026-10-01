from __future__ import annotations

import getpass
import os
import shutil
from pathlib import Path

from .config import AppConfig, DEFAULT_CONFIG_PATH, NotionSettings, TerminalSettings, write_config
from .notion import NotionClient, parse_page_id


def run_init(config_path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    print("notion_is_terminal setup")
    print("Creates one Notion page containing exactly two code blocks: Terminal + Input.\n")

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
        columns=columns,
        rows=rows,
        poll_interval=poll_interval,
        refresh_interval=refresh_interval,
        show_cursor=True,
        source_bashrc=True,
    )
    prompt = f"{user}@{host}:{cwd}$ "

    print("\nChecking Notion access and creating page...")
    with NotionClient(token) as notion:
        notion.get_page(parent_page_id)
        created = notion.create_terminal_page(
            parent_page_id=parent_page_id,
            title=title,
            terminal_text="notion_is_terminal\n\nLocal PTY is not connected yet. Run: notion-terminal run",
            input_text=prompt,
        )

    config = AppConfig(
        notion=NotionSettings(
            token=token,
            page_id=created.page_id,
            terminal_block_id=created.terminal_block_id,
            input_block_id=created.input_block_id,
            page_url=created.page_url,
        ),
        terminal=terminal,
    )
    written = write_config(config, config_path)

    print("\n✓ Notion connection verified")
    print("✓ Terminal page created")
    print("✓ Terminal code block created")
    print("✓ Input code block created")
    print(f"✓ Config written: {written}")
    if created.page_url:
        print(f"\nPage: {created.page_url}")
    print("\nStart the daemon with:\n  notion-terminal run")
    print("\nInput rule: type in Input, then press Enter twice to send.")
    print("Ctrl-C can be sent immediately by typing ^C after the prompt.")
    return config


def _prompt(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default
