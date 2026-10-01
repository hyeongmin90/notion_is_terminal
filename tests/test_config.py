from pathlib import Path

from notion_is_terminal.config import AppConfig, NotionSettings, TerminalSettings, load_config, write_config


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    config = AppConfig(
        notion=NotionSettings(
            token="secret_test",
            page_id="page",
            terminal_block_id="terminal",
            input_block_id="input",
            page_url="https://notion.so/test",
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
        ),
    )
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.notion.token == "secret_test"
    assert loaded.terminal.input_prompt == "> "
    assert loaded.terminal.columns == 100
    assert loaded.terminal.rows == 30
    assert loaded.terminal.health_check_interval == 12.0


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
