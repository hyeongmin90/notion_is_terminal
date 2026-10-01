from notion_is_terminal.notion import (
    MAX_RICH_TEXT_CHUNK,
    NotionClient,
    NotionError,
    RuntimeBlocks,
    block_is_usable_code,
    parse_page_id,
    rich_text_payload,
    terminal_page_children,
)


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


def test_generated_page_has_exactly_two_code_blocks():
    children = terminal_page_children("screen", "user@ubuntu:/home$ ")
    code_blocks = [block for block in children if block["type"] == "code"]
    assert len(code_blocks) == 2
    assert code_blocks[0]["code"]["language"] == "plain text"
    assert code_blocks[1]["code"]["language"] == "bash"


def test_block_usability_rejects_archived_or_trashed_blocks():
    assert block_is_usable_code({"type": "code", "archived": False, "in_trash": False})
    assert not block_is_usable_code({"type": "code", "archived": True})
    assert not block_is_usable_code({"type": "code", "in_trash": True})
    assert not block_is_usable_code({"type": "paragraph"})


def test_notion_error_marks_object_not_found():
    exc = NotionError("missing", status_code=404, code="object_not_found")
    assert exc.is_not_found


class FakeNotionClient(NotionClient):
    def __init__(self):
        self.blocks = {
            "input-old": {"id": "input-old", "type": "code", "archived": False, "in_trash": False}
        }
        self.archived = []
        self.appended = False

    def get_page(self, page_id):
        assert page_id == "page"
        return {"id": page_id}

    def get_block(self, block_id):
        if block_id not in self.blocks:
            raise NotionError("missing", status_code=404, code="object_not_found")
        return self.blocks[block_id]

    def archive_block(self, block_id):
        self.archived.append(block_id)
        self.blocks[block_id]["archived"] = True

    def append_runtime_blocks(self, *, page_id, terminal_text, input_text):
        assert page_id == "page"
        assert terminal_text == "current screen"
        assert input_text == "user@ubuntu:/home$ "
        self.appended = True
        return RuntimeBlocks("terminal-new", "input-new", recreated=True)


def test_missing_runtime_block_recreates_pair_and_archives_survivor():
    notion = FakeNotionClient()
    blocks = notion.ensure_runtime_blocks(
        page_id="page",
        terminal_block_id="terminal-missing",
        input_block_id="input-old",
        terminal_text="current screen",
        input_text="user@ubuntu:/home$ ",
    )

    assert notion.appended is True
    assert notion.archived == ["input-old"]
    assert blocks.recreated is True
    assert blocks.terminal_block_id == "terminal-new"
    assert blocks.input_block_id == "input-new"
