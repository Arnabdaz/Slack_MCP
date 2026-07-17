"""Tests for pure message-formatting helpers."""

from __future__ import annotations

from typing import Any

from slack_mcp_server.formatting import (
    collect_user_ids,
    format_message,
    format_thread,
    substitute_mentions,
)


def _msg(user: str, text: str, ts: str = "1.0") -> dict[str, Any]:
    return {"user": user, "text": text, "ts": ts}


class TestCollectUserIds:
    def test_unique_and_skips_empty(self) -> None:
        msgs = [_msg("U1", "a"), _msg("U2", "b"), _msg("U1", "c"), {"text": "no user"}]
        assert sorted(collect_user_ids(msgs)) == ["U1", "U2"]


class TestSubstituteMentions:
    def test_known_mention_replaced(self) -> None:
        out = substitute_mentions("hey <@U1> look", {"U1": "alice"})
        assert out == "hey @alice look"

    def test_unknown_mention_left_as_is(self) -> None:
        out = substitute_mentions("hey <@U9>", {})
        assert "<@U9>" in out


class TestFormatMessage:
    def test_includes_author_and_text(self) -> None:
        out = format_message(_msg("U1", "hello <@U2>"), {"U1": "alice", "U2": "bob"})
        assert "alice" in out
        assert "hello @bob" in out

    def test_includes_permalink_when_given(self) -> None:
        out = format_message(_msg("U1", "hi"), {"U1": "alice"}, permalink="https://x/p/1")
        assert "https://x/p/1" in out


class TestFormatThread:
    def test_renders_all_messages_in_order(self) -> None:
        msgs = [_msg("U1", "root", "1.0"), _msg("U2", "reply", "2.0")]
        out = format_thread(msgs, {"U1": "alice", "U2": "bob"}, channel_name="eng")
        assert out.index("root") < out.index("reply")
        assert "alice" in out and "bob" in out
