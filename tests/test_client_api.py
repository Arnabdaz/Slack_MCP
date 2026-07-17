"""Tests for SlackClient API methods and the user-name cache."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from slack_mcp_server.client import ScopeError, SlackClient


def _client(web: Any) -> SlackClient:
    return SlackClient(token="xoxp-test", web_client=web)


class TestSearchMessages:
    async def test_filters_out_non_public_matches(self) -> None:
        web = AsyncMock()
        web.search_messages = AsyncMock(
            return_value={
                "messages": {
                    "matches": [
                        {
                            "ts": "1",
                            "text": "public hit",
                            "channel": {
                                "id": "C1",
                                "name": "eng",
                                "is_channel": True,
                                "is_private": False,
                            },
                        },
                        {
                            "ts": "2",
                            "text": "private hit",
                            "channel": {
                                "id": "C2",
                                "name": "secret",
                                "is_channel": True,
                                "is_private": True,
                            },
                        },
                        {"ts": "3", "text": "dm hit", "channel": {"id": "D1", "is_im": True}},
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
            return_value={
                "user": {"id": "U1", "profile": {"display_name": "alice"}, "real_name": "Alice A"}
            }
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
            return_value={
                "user": {"id": "U2", "profile": {"display_name": ""}, "real_name": "Bob B"}
            }
        )
        names = await _client(web).resolve_users(["U2"])
        assert names == {"U2": "Bob B"}


class TestConversationsReplies:
    async def test_returns_messages_list(self) -> None:
        web = AsyncMock()
        web.conversations_info = AsyncMock(
            return_value={
                "channel": {"id": "C1", "name": "eng", "is_channel": True, "is_private": False}
            }
        )
        web.conversations_replies = AsyncMock(
            return_value={"messages": [{"ts": "1", "text": "root"}, {"ts": "2", "text": "reply"}]}
        )
        client = _client(web)
        msgs = await client.conversations_replies("C1", "1")
        assert [m["text"] for m in msgs] == ["root", "reply"]


class TestPostMessage:
    async def test_returns_ts_and_channel(self) -> None:
        web = AsyncMock()
        web.conversations_info = AsyncMock(
            return_value={
                "channel": {"id": "C1", "name": "eng", "is_channel": True, "is_private": False}
            }
        )
        web.chat_postMessage = AsyncMock(return_value={"ts": "99.1", "channel": "C1"})
        client = _client(web)
        result = await client.post_message("C1", "hello", thread_ts="1.0")
        assert result["ts"] == "99.1"
        web.chat_postMessage.assert_awaited_once_with(channel="C1", text="hello", thread_ts="1.0")


class TestScopeGuardOnApiMethods:
    """Verify that the scope guard blocks private channels and allows pre-validated ones."""

    def _make_client_private(self) -> tuple[Any, SlackClient]:
        """Return (web, client) where conversations_info reports a private channel."""
        web = AsyncMock()
        web.conversations_info = AsyncMock(
            return_value={
                "channel": {
                    "id": "C9",
                    "name": "secret",
                    "is_channel": True,
                    "is_private": True,
                }
            }
        )
        return web, _client(web)

    async def test_conversations_replies_blocks_private(self) -> None:
        _, client = self._make_client_private()
        with pytest.raises(ScopeError):
            await client.conversations_replies("C9", "1.0")

    async def test_conversations_history_blocks_private(self) -> None:
        _, client = self._make_client_private()
        with pytest.raises(ScopeError):
            await client.conversations_history("C9")

    async def test_get_permalink_blocks_private(self) -> None:
        _, client = self._make_client_private()
        with pytest.raises(ScopeError):
            await client.get_permalink("C9", "1.0")

    async def test_post_message_blocks_private(self) -> None:
        _, client = self._make_client_private()
        with pytest.raises(ScopeError):
            await client.post_message("C9", "hello")

    async def test_no_drift_revalidates_every_call(self) -> None:
        """Guard re-validates on every call — stale public state does not persist."""
        web = AsyncMock()
        public_channel = {
            "channel": {"id": "C1", "name": "eng", "is_channel": True, "is_private": False}
        }
        private_channel = {
            "channel": {"id": "C1", "name": "eng", "is_channel": True, "is_private": True}
        }
        web.conversations_info = AsyncMock(side_effect=[public_channel, private_channel])
        web.conversations_history = AsyncMock(
            return_value={"messages": [{"ts": "1", "text": "hi"}]}
        )
        client = _client(web)
        # First call: channel is public — should succeed
        msgs = await client.conversations_history("C1")
        assert msgs[0]["text"] == "hi"
        # Second call: channel is now private — guard must catch it
        with pytest.raises(ScopeError):
            await client.conversations_history("C1")
