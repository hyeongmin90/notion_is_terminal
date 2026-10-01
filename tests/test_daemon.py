from notion_is_terminal.daemon import sanitize_terminal_for_notion


def test_sanitize_terminal_for_notion_leaves_normal_text_unchanged():
    assert sanitize_terminal_for_notion("hello\\nworld") == "hello\\nworld"


def test_sanitize_terminal_for_notion_breaks_markdown_fences():
    value = sanitize_terminal_for_notion("before ```python after")
    assert "```" not in value
    assert value.replace("\\u200b", "") == "before ```python after"


def test_sanitize_terminal_for_notion_breaks_long_backtick_runs():
    value = sanitize_terminal_for_notion("``````")
    assert "```" not in value
    assert value.replace("\\u200b", "") == "``````"
