from notion_is_terminal.notion import MAX_RICH_TEXT_CHUNK, parse_page_id, rich_text_payload


def test_parse_plain_uuid():
    value = "123456781234123412341234567890ab"
    assert parse_page_id(value) == "12345678-1234-1234-1234-1234567890ab"


def test_parse_notion_url():
    url = "https://www.notion.so/Test-123456781234123412341234567890ab?pvs=4"
    assert parse_page_id(url) == "12345678-1234-1234-1234-1234567890ab"


def test_rich_text_is_chunked_below_notion_limit():
    text = "x" * (MAX_RICH_TEXT_CHUNK + 10)
    payload = rich_text_payload(text)
    assert len(payload) == 2
    assert "".join(item["text"]["content"] for item in payload) == text
    assert all(len(item["text"]["content"]) <= MAX_RICH_TEXT_CHUNK for item in payload)
