from notion_is_terminal.notion import (
    MAX_RICH_TEXT_CHUNK,
    NotionClient,
    NotionError,
    RuntimeAnchors,
    RuntimeBlocks,
    block_is_usable_code,
    find_runtime_anchors,
    parse_page_id,
    rich_text_payload,
    runtime_blocks_are_in_place,
    terminal_page_children,
)


def _rich(text):
    return [{"plain_text": text}]


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
    children = terminal_page_children("screen", "> ")
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


def test_find_runtime_anchors_and_positions():
    children = [
        {"id": "h-terminal", "type": "heading_2", "heading_2": {"rich_text": _rich("Terminal")}},
        {"id": "a-terminal", "type": "paragraph", "paragraph": {"rich_text": _rich("Live PTY")}},
        {"id": "terminal", "type": "code", "code": {"rich_text": []}},
        {"id": "h-input", "type": "heading_2", "heading_2": {"rich_text": _rich("Input")}},
        {"id": "a-input", "type": "paragraph", "paragraph": {"rich_text": _rich("Input help")}},
        {"id": "input", "type": "code", "code": {"rich_text": []}},
    ]

    anchors = find_runtime_anchors(children)
    assert anchors == RuntimeAnchors("a-terminal", "a-input")
    assert runtime_blocks_are_in_place(
        children,
        terminal_anchor_id="a-terminal",
        input_anchor_id="a-input",
        terminal_block_id="terminal",
        input_block_id="input",
    )


def test_runtime_pair_at_page_end_is_not_considered_in_place():
    children = [
        {"id": "h-terminal", "type": "heading_2", "heading_2": {"rich_text": _rich("Terminal")}},
        {"id": "a-terminal", "type": "paragraph", "paragraph": {"rich_text": _rich("Live PTY")}},
        {"id": "h-input", "type": "heading_2", "heading_2": {"rich_text": _rich("Input")}},
        {"id": "a-input", "type": "paragraph", "paragraph": {"rich_text": _rich("Input help")}},
        {"id": "terminal-old", "type": "code", "code": {"rich_text": []}},
        {"id": "input-old", "type": "code", "code": {"rich_text": []}},
    ]
    assert not runtime_blocks_are_in_place(
        children,
        terminal_anchor_id="a-terminal",
        input_anchor_id="a-input",
        terminal_block_id="terminal-old",
        input_block_id="input-old",
    )


class FakeNotionClient(NotionClient):
    def __init__(self):
        self.blocks = {
            "input-old": {"id": "input-old", "type": "code", "archived": False, "in_trash": False}
        }
        self.archived = []
        self.restored = False

    def get_page(self, page_id):
        assert page_id == "page"
        return {"id": page_id}

    def get_block(self, block_id):
        if block_id not in self.blocks:
            raise NotionError("missing", status_code=404, code="object_not_found")
        return self.blocks[block_id]

    def get_block_children(self, block_id):
        assert block_id == "page"
        return [
            {"id": "h-terminal", "type": "heading_2", "heading_2": {"rich_text": _rich("Terminal")}},
            {"id": "a-terminal", "type": "paragraph", "paragraph": {"rich_text": _rich("Live PTY")}},
            {"id": "h-input", "type": "heading_2", "heading_2": {"rich_text": _rich("Input")}},
            {"id": "a-input", "type": "paragraph", "paragraph": {"rich_text": _rich("Input help")}},
            self.blocks["input-old"],
        ]

    def archive_block(self, block_id):
        self.archived.append(block_id)
        self.blocks[block_id]["archived"] = True

    def restore_runtime_blocks_at_anchors(self, *, page_id, anchors, terminal_text, input_text):
        assert page_id == "page"
        assert anchors == RuntimeAnchors("a-terminal", "a-input")
        assert terminal_text == "current screen"
        assert input_text == "> "
        self.restored = True
        return RuntimeBlocks("terminal-new", "input-new", recreated=True)


def test_missing_runtime_block_restores_pair_at_anchors_and_archives_survivor():
    notion = FakeNotionClient()
    blocks = notion.ensure_runtime_blocks(
        page_id="page",
        terminal_block_id="terminal-missing",
        input_block_id="input-old",
        terminal_text="current screen",
        input_text="> ",
    )

    assert notion.restored is True
    assert notion.archived == ["input-old"]
    assert blocks.recreated is True
    assert blocks.terminal_block_id == "terminal-new"
    assert blocks.input_block_id == "input-new"
