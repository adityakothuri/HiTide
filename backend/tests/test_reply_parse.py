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


@pytest.mark.parametrize("text,want", [("No.", "need_help"), ("Nope, the water's rising", "need_help"),
                                       ("nah", "need_help"), ("no, I'm fine", "safe"), ("know", None)])
def test_spoken_reply_bare_no_is_need_help(text, want):
    from outreach.replies import parse_spoken_reply
    assert parse_spoken_reply(text) == want


def test_texted_bare_no_is_unchanged():
    """Texts ask for SAFE/HELP explicitly; only the voice agent's "Are you okay?" makes a bare "no" meaningful."""
    assert parse_reply("No") is None
