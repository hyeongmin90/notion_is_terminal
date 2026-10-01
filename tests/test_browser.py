import pytest

from notion_is_terminal.browser import BrowserController, BrowserError, parse_browser_command
from notion_is_terminal.config import BrowserSettings


def test_parse_browser_command():
    name, args = parse_browser_command("click obs_1 100 200")
    assert name == "click"
    assert args == ["obs_1", "100", "200"]


def test_parse_browser_command_rejects_empty():
    with pytest.raises(BrowserError):
        parse_browser_command("")


def test_coordinate_validation_rejects_outside_viewport():
    controller = BrowserController(BrowserSettings(width=1280, height=720))
    with pytest.raises(BrowserError, match="outside viewport"):
        controller._coordinate_args(
            ["obs_1", "1281", "10"],
            2,
            "click <observation_id> <x> <y>",
        )


def test_stale_observation_is_rejected():
    controller = BrowserController(BrowserSettings())
    controller._observation_id = "obs_latest"
    with pytest.raises(BrowserError, match="STALE_OBSERVATION"):
        controller._assert_observation("obs_old")
