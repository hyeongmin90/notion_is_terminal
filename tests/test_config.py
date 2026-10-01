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
            columns=100,
            rows=30,
            poll_interval=1.0,
            refresh_interval=1.5,
        ),
    )
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.notion.token == "secret_test"
    assert loaded.terminal.columns == 100
    assert loaded.terminal.rows == 30
