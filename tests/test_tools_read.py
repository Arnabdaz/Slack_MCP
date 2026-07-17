"""Tests for read tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_client(**methods: Any) -> MagicMock:
    client = MagicMock()
    for name, value in methods.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


class TestSearchMessages:
    async def test_formats_matches(self) -> None:
        from slack_mcp_server.tools import search_messages

        client = _mock_client(
            search_messages=[
                {
                    "ts": "1.0",
                    "text": "DSE-1 is fixed",
                    "user": "U1",
                    "channel": {"id": "C1", "name": "eng"},
                    "permalink": "https://x/p/1",
                },
            ],
            resolve_users={"U1": "alice"},
        )
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await search_messages("DSE-1")
        assert "result" in result
        assert "alice" in result["result"]
        assert "DSE-1 is fixed" in result["result"]

    async def test_no_matches_message(self) -> None:
        from slack_mcp_server.tools import search_messages

        client = _mock_client(search_messages=[], resolve_users={})
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await search_messages("nothing")
        assert "No messages" in result["result"]


class TestReadThread:
    async def test_scope_error_returns_error_dict(self) -> None:
        from slack_mcp_server.client import ScopeError
        from slack_mcp_server.tools import read_thread

        client = MagicMock()
        client.resolve_channel = AsyncMock(side_effect=ScopeError("not public"))
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await read_thread("C2", "1.0")
        assert "error" in result
        assert "not public" in result["error"]

    async def test_renders_thread(self) -> None:
        from slack_mcp_server.tools import read_thread

        client = MagicMock()
        client.resolve_channel = AsyncMock(return_value={"id": "C1", "name": "eng"})
        client.conversations_replies = AsyncMock(
            return_value=[
                {"user": "U1", "text": "root", "ts": "1.0"},
                {"user": "U2", "text": "reply", "ts": "2.0"},
            ]
        )
        client.resolve_users = AsyncMock(return_value={"U1": "alice", "U2": "bob"})
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await read_thread("C1", "1.0")
        assert "root" in result["result"]
        assert "reply" in result["result"]


class TestListChannels:
    async def test_lists_names(self) -> None:
        from slack_mcp_server.tools import list_channels

        client = _mock_client(
            list_public_channels=[{"id": "C1", "name": "eng-prs", "topic": "PRs"}]
        )
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await list_channels()
        assert "eng-prs" in result["result"]
