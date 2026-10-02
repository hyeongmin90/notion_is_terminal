from terminal4gptweb.protocol import InputKind, decode_escapes, extract_submission


PROMPT = "> "


def test_partial_text_is_not_submitted():
    action, reset = extract_submission(PROMPT + "kubectl get po", PROMPT)
    assert action is None
    assert reset is False


def test_normal_command_requires_blank_line():
    action, reset = extract_submission(PROMPT + "pwd\n\n", PROMPT)
    assert reset is True
    assert action is not None
    assert action.kind is InputKind.LINE
    assert action.value == "pwd"


def test_ctrl_c_is_immediate():
    action, reset = extract_submission(PROMPT + "^C", PROMPT)
    assert reset is True
    assert action is not None
    assert action.kind is InputKind.CONTROL
    assert action.value == "C"


def test_key_command():
    action, _ = extract_submission(PROMPT + ":key UP\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.KEY
    assert action.value == "UP"


def test_short_key_command():
    action, _ = extract_submission(PROMPT + ":k ENTER\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.KEY
    assert action.value == "ENTER"


def test_short_ctrl_command():
    action, _ = extract_submission(PROMPT + ":c O\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.CONTROL
    assert action.value == "O"


def test_raw_escape_decode():
    action, _ = extract_submission(PROMPT + r":send \e:wq\r" + "\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.RAW
    assert action.value == "\x1b:wq\r"


def test_short_raw_command():
    action, _ = extract_submission(PROMPT + r":s \e:q!\r" + "\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.RAW
    assert action.value == "\x1b:q!\r"


def test_resize():
    action, _ = extract_submission(PROMPT + ":resize 100x30\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.RESIZE
    assert action.columns == 100
    assert action.rows == 30


def test_short_resize():
    action, _ = extract_submission(PROMPT + ":rs 120x40\n\n", PROMPT)
    assert action is not None
    assert action.kind is InputKind.RESIZE
    assert action.columns == 120
    assert action.rows == 40


def test_decode_escapes_preserves_unicode():
    assert decode_escapes(r"한글\n") == "한글\n"


def test_browser_short_command():
    action, reset = extract_submission(PROMPT + ":b shot\n\n", PROMPT)
    assert reset is True
    assert action is not None
    assert action.kind is InputKind.BROWSER
    assert action.value == "shot"


def test_browser_long_command_preserves_arguments():
    action, _ = extract_submission(
        PROMPT + ":browser click obs_1 120 240\n\n",
        PROMPT,
    )
    assert action is not None
    assert action.kind is InputKind.BROWSER
    assert action.value == "click obs_1 120 240"
