"""Tests for the public-channel-only scope guard."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from slack_mcp_server.client import (
    ScopeError,
    SlackClient,
    get_slack_client,
    is_public_channel,
)


def _public() -> dict[str, Any]:
    return {"id": "C1", "name": "eng-prs", "is_channel": True, "is_private": False}


def _private() -> dict[str, Any]:
    return {"id": "C2", "name": "secret", "is_channel": True, "is_private": True}


def _dm() -> dict[str, Any]:
    return {"id": "D1", "is_im": True}


def _mpim() -> dict[str, Any]:
    return {"id": "C3", "is_mpim": True, "is_private": True}


class TestIsPublicChannel:
    def test_public_is_true(self) -> None:
        assert is_public_channel(_public()) is True

    def test_private_is_false(self) -> None:
        assert is_public_channel(_private()) is False

    def test_dm_is_false(self) -> None:
        assert is_public_channel(_dm()) is False

    def test_mpim_is_false(self) -> None:
        assert is_public_channel(_mpim()) is False


class TestResolveChannel:
    async def _client_with_info(self, channel_obj: dict[str, Any]) -> SlackClient:
        web = AsyncMock()
        web.conversations_info = AsyncMock(return_value={"channel": channel_obj})
        return SlackClient(token="xoxp-test", web_client=web)

    async def test_public_channel_id_resolves(self) -> None:
        client = await self._client_with_info(_public())
        obj = await client.resolve_channel("C1")
        assert obj["id"] == "C1"

    async def test_private_channel_raises(self) -> None:
        client = await self._client_with_info(_private())
        with pytest.raises(ScopeError):
            await client.resolve_channel("C2")

    async def test_dm_raises(self) -> None:
        client = await self._client_with_info(_dm())
        with pytest.raises(ScopeError):
            await client.resolve_channel("D1")

    async def test_name_resolves_via_list(self) -> None:
        web = AsyncMock()
        web.conversations_list = AsyncMock(
            return_value={
                "channels": [{"id": "C1", "name": "eng-prs"}],
                "response_metadata": {"next_cursor": ""},
            }
        )
        web.conversations_info = AsyncMock(return_value={"channel": _public()})
        client = SlackClient(token="xoxp-test", web_client=web)
        obj = await client.resolve_channel("#eng-prs")
        assert obj["id"] == "C1"
        web.conversations_list.assert_awaited()


class TestGetSlackClient:
    def test_missing_token_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="SLACK_USER_TOKEN"):
            get_slack_client()
