import pytest

from outreach.replies import parse_reply


@pytest.mark.parametrize("text", ["I'm safe", "safe", "SAFE", "ok", "Ok.", "okay", "We're fine, all safe now"])
def test_safe_replies(text):
    assert parse_reply(text) == "safe"


@pytest.mark.parametrize("text", ["I need help", "HELP", "sos", "not safe", "unsafe", "I'm not ok", "not okay",
                                  "water rising help", "safe? no, help"])
def test_need_help_replies(text):
    assert parse_reply(text) == "need_help"


@pytest.mark.parametrize("text", ["", "who is this?", "safety first lol", "helpful"])
def test_unrelated_text_is_ignored(text):
    assert parse_reply(text) is None
