from pathlib import Path

from notion_is_terminal.config import (
    AppConfig,
    NotionSettings,
    SandboxSettings,
    TerminalSettings,
    load_config,
    write_config,
)


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    config = AppConfig(
        notion=NotionSettings(
            token="secret_test",
            page_id="page",
            terminal_block_id="terminal",
            input_block_id="input",
            page_url="https://notion.so/test",
            parent_page_id="parent",
            help_page_id="help",
            help_page_url="https://notion.so/help",
        ),
        terminal=TerminalSettings(
            shell="/bin/bash",
            cwd="/tmp",
            user="user",
            host="ubuntu",
            input_prompt="> ",
            columns=100,
            rows=30,
            poll_interval=1.0,
            refresh_interval=1.5,
            health_check_interval=12.0,
            sandbox=SandboxSettings(
                mode="workspace",
                workspace="/tmp/project",
                deny_read=[".env"],
                deny_write=[".git"],
            ),
        ),
    )
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.notion.token == "secret_test"
    assert loaded.notion.parent_page_id == "parent"
    assert loaded.notion.help_page_id == "help"
    assert loaded.notion.help_page_url == "https://notion.so/help"
    assert loaded.terminal.input_prompt == "> "
    assert loaded.terminal.sandbox.mode == "none"
    assert loaded.terminal.sandbox.deny_read == []
    assert loaded.terminal.sandbox.deny_write == []
    assert loaded.terminal.columns == 100
    assert loaded.terminal.rows == 30
    assert loaded.terminal.health_check_interval == 12.0
    assert loaded.terminal.sandbox.mode == "workspace"
    assert loaded.terminal.sandbox.workspace == "/tmp/project"
    assert loaded.terminal.sandbox.deny_read == [".env"]
    assert loaded.terminal.sandbox.deny_write == [".git"]
    assert loaded.browser.width == 1280
    assert loaded.browser.height == 720


def test_old_config_defaults_to_compact_input_prompt(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[notion]
token = "secret_test"
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
shell = "/bin/bash"
cwd = "/tmp"
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(path)
    assert loaded.terminal.input_prompt == "> "


def test_old_config_gets_browser_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[notion]
token = "secret_test"
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
shell = "/bin/bash"
cwd = "/tmp"
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(path)
    assert loaded.notion.parent_page_id == ""
    assert loaded.notion.help_page_id == ""
    assert loaded.notion.help_page_url == ""
    assert loaded.notion.browser_status_block_id == ""
    assert loaded.notion.browser_image_block_id == ""
    assert loaded.browser.width == 1280
    assert loaded.browser.height == 720
    assert loaded.browser.headless is True
    assert loaded.browser.vision_enabled is True
    assert loaded.browser.vision_quality == 35
    assert loaded.notion.browser_vision_page_id == ""
    assert loaded.notion.browser_vision_block_id == ""
