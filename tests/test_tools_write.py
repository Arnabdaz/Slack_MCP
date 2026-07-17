"""Tests for write tools and the two-step confirmation guard."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slack_mcp_server import confirm


@pytest.fixture(autouse=True)
def _fresh_store() -> Any:
    """Give each test an isolated draft store."""
    original = confirm.drafts
    confirm.drafts = confirm.DraftStore(ttl_seconds=300)
    yield
    confirm.drafts = original


def _client() -> MagicMock:
    client = MagicMock()
    client.resolve_channel = AsyncMock(return_value={"id": "C1", "name": "eng-prs"})
    client.post_message = AsyncMock(return_value={"ts": "99.1", "channel": "C1"})
    client.get_permalink = AsyncMock(return_value="https://x/p/99")
    return client


class TestDraftMessage:
    async def test_draft_does_not_post_and_returns_token(self) -> None:
        from slack_mcp_server.tools import draft_message

        client = _client()
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await draft_message("#eng-prs", "Ship it")
        assert "result" in result
        assert "Ship it" in result["result"]
        client.post_message.assert_not_called()
        # exactly one draft is now pending
        assert len(confirm.drafts._entries) == 1  # noqa: SLF001

    async def test_scope_error_surfaces(self) -> None:
        from slack_mcp_server.client import ScopeError
        from slack_mcp_server.tools import draft_message

        client = MagicMock()
        client.resolve_channel = AsyncMock(side_effect=ScopeError("not public"))
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await draft_message("C2", "hi")
        assert "error" in result
        assert "not public" in result["error"]


class TestSendMessage:
    async def test_send_with_valid_token_posts_once(self) -> None:
        from slack_mcp_server.tools import draft_message, send_message

        client = _client()
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            draft = await draft_message("#eng-prs", "Ship it")
            token = confirm.drafts._entries  # noqa: SLF001
            (the_token,) = token.keys()
            result = await send_message(the_token)
        assert "result" in result
        assert "https://x/p/99" in result["result"]
        client.post_message.assert_awaited_once_with("C1", "Ship it", thread_ts=None)

    async def test_send_with_bad_token_does_not_post(self) -> None:
        from slack_mcp_server.tools import send_message

        client = _client()
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            result = await send_message("bogus-token")
        assert "error" in result
        client.post_message.assert_not_called()

    async def test_token_is_single_use(self) -> None:
        from slack_mcp_server.tools import draft_message, send_message

        client = _client()
        with patch("slack_mcp_server.tools.get_slack_client", return_value=client):
            await draft_message("#eng-prs", "Ship it")
            (the_token,) = confirm.drafts._entries.keys()  # noqa: SLF001
            await send_message(the_token)
            second = await send_message(the_token)
        assert "error" in second
        client.post_message.assert_awaited_once()
