"""Tests for SlackClient API methods and the user-name cache."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from slack_mcp_server.client import SlackClient


def _client(web: Any) -> SlackClient:
    return SlackClient(token="xoxp-test", web_client=web)


class TestSearchMessages:
    async def test_filters_out_non_public_matches(self) -> None:
        web = AsyncMock()
        web.search_messages = AsyncMock(
            return_value={
                "messages": {
                    "matches": [
                        {"ts": "1", "text": "public hit",
                         "channel": {"id": "C1", "name": "eng", "is_channel": True, "is_private": False}},
                        {"ts": "2", "text": "private hit",
                         "channel": {"id": "C2", "name": "secret", "is_channel": True, "is_private": True}},
                        {"ts": "3", "text": "dm hit",
                         "channel": {"id": "D1", "is_im": True}},
                    ]
                }
            }
        )
        matches = await _client(web).search_messages("DSE-1234")
        assert [m["ts"] for m in matches] == ["1"]


class TestResolveUsers:
    async def test_caches_and_avoids_second_call(self) -> None:
        web = AsyncMock()
        web.users_info = AsyncMock(
            return_value={"user": {"id": "U1", "profile": {"display_name": "alice"}, "real_name": "Alice A"}}
        )
        client = _client(web)
        first = await client.resolve_users(["U1"])
        second = await client.resolve_users(["U1"])
        assert first == {"U1": "alice"}
        assert second == {"U1": "alice"}
        web.users_info.assert_awaited_once()  # cached on the second call

    async def test_falls_back_to_real_name_then_id(self) -> None:
        web = AsyncMock()
        web.users_info = AsyncMock(
            return_value={"user": {"id": "U2", "profile": {"display_name": ""}, "real_name": "Bob B"}}
        )
        names = await _client(web).resolve_users(["U2"])
        assert names == {"U2": "Bob B"}


class TestConversationsReplies:
    async def test_returns_messages_list(self) -> None:
        web = AsyncMock()
        web.conversations_replies = AsyncMock(
            return_value={"messages": [{"ts": "1", "text": "root"}, {"ts": "2", "text": "reply"}]}
        )
        msgs = await _client(web).conversations_replies("C1", "1")
        assert [m["text"] for m in msgs] == ["root", "reply"]


class TestPostMessage:
    async def test_returns_ts_and_channel(self) -> None:
        web = AsyncMock()
        web.chat_postMessage = AsyncMock(return_value={"ts": "99.1", "channel": "C1"})
        result = await _client(web).post_message("C1", "hello", thread_ts="1.0")
        assert result["ts"] == "99.1"
        web.chat_postMessage.assert_awaited_once_with(channel="C1", text="hello", thread_ts="1.0")
