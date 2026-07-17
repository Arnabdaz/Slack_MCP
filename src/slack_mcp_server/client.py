"""Slack Web API client wrapper with a public-channel-only scope guard.

All channel access flows through `resolve_channel`, which refuses anything that
is not a public channel. This is the enforcement point for the server's read
restriction — it is never delegated to the caller/model.
"""

from __future__ import annotations

import os
import re
from typing import Any

from slack_sdk.errors import SlackApiError as _SdkSlackApiError
from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
from slack_sdk.web.async_client import AsyncWebClient

_CHANNEL_ID_RE = re.compile(r"^[CGD][A-Z0-9]+$")


class ScopeError(Exception):
    """Raised when a caller tries to access a non-public channel."""


class SlackApiError(Exception):
    """Raised when the Slack API returns an error response."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def is_public_channel(channel_obj: dict[str, Any]) -> bool:
    """Return True only for public channels (not private, DM, group DM, or legacy group)."""
    if not channel_obj.get("is_channel", False):
        return False
    return not (
        channel_obj.get("is_private", False)
        or channel_obj.get("is_im", False)
        or channel_obj.get("is_mpim", False)
        or channel_obj.get("is_group", False)
    )


class SlackClient:
    """Async Slack Web API client scoped to public channels for reads."""

    def __init__(self, token: str, *, web_client: Any | None = None) -> None:
        if web_client is not None:
            self._web: AsyncWebClient = web_client
        else:
            self._web = AsyncWebClient(token=token)
            self._web.retry_handlers.append(
                AsyncRateLimitErrorRetryHandler(max_retry_count=3)
            )
        self._user_names: dict[str, str] = {}

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        session = getattr(self._web, "session", None)
        if session is not None and not session.closed:
            await session.close()

    async def _resolve_name_to_id(self, name: str) -> str:
        """Look up a public channel id by name via paginated conversations.list."""
        cursor = ""
        while True:
            try:
                resp = await self._web.conversations_list(
                    types="public_channel",
                    limit=200,
                    cursor=cursor or None,
                )
            except _SdkSlackApiError as e:  # pragma: no cover - exercised in Task 4 tests
                msg = f"Slack API error: {e.response['error']}"
                raise SlackApiError(msg) from e
            for ch in resp["channels"]:
                if ch.get("name") == name:
                    return str(ch["id"])
            meta: dict[str, Any] = resp.get("response_metadata") or {}
            cursor = meta.get("next_cursor", "")
            if not cursor:
                break
        msg = f"No public channel named '{name}' was found."
        raise ScopeError(msg)

    async def resolve_channel(self, channel: str) -> dict[str, Any]:
        """Return the channel object for `channel` (id or #name), or raise ScopeError.

        Raises ScopeError if the resolved channel is not a public channel.
        """
        raw = channel.lstrip("#")
        channel_id = raw if _CHANNEL_ID_RE.match(raw) else await self._resolve_name_to_id(raw)
        try:
            resp = await self._web.conversations_info(channel=channel_id)
        except _SdkSlackApiError as e:
            msg = f"Slack API error: {e.response['error']}"
            raise SlackApiError(msg) from e
        obj: dict[str, Any] = resp["channel"]
        if not is_public_channel(obj):
            msg = (
                f"Channel '{channel}' is not a public channel. "
                "This server only accesses public channels."
            )
            raise ScopeError(msg)
        return obj

    async def search_messages(self, query: str, count: int = 20) -> list[dict[str, Any]]:
        """Search messages (search.messages); return only public-channel matches."""
        try:
            resp = await self._web.search_messages(query=query, count=count)
        except _SdkSlackApiError as e:
            msg = f"Slack API error: {e.response['error']}"
            raise SlackApiError(msg) from e
        messages_obj: dict[str, Any] = resp.get("messages") or {}
        matches: list[dict[str, Any]] = messages_obj.get("matches") or []
        return [m for m in matches if is_public_channel(m.get("channel") or {})]

    async def conversations_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        """Return a thread's messages (root + replies)."""
        try:
            resp = await self._web.conversations_replies(channel=channel_id, ts=thread_ts)
        except _SdkSlackApiError as e:
            msg = f"Slack API error: {e.response['error']}"
            raise SlackApiError(msg) from e
        return list(resp.get("messages", []))

    async def conversations_history(
        self, channel_id: str, limit: int = 30, around_ts: str | None = None
    ) -> list[dict[str, Any]]:
        """Return recent messages, or a window ending at `around_ts` when given."""
        kwargs: dict[str, Any] = {"channel": channel_id, "limit": limit}
        if around_ts is not None:
            kwargs["latest"] = around_ts
            kwargs["inclusive"] = True
        try:
            resp = await self._web.conversations_history(**kwargs)
        except _SdkSlackApiError as e:
            msg = f"Slack API error: {e.response['error']}"
            raise SlackApiError(msg) from e
        return list(resp.get("messages", []))

    async def list_public_channels(
        self, name_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Return public channels (id, name, topic), optionally substring-filtered by name."""
        out: list[dict[str, Any]] = []
        cursor = ""
        needle = name_filter.lower() if name_filter else None
        while True:
            try:
                resp = await self._web.conversations_list(
                    types="public_channel", limit=200, cursor=cursor or None
                )
            except _SdkSlackApiError as e:
                msg = f"Slack API error: {e.response['error']}"
                raise SlackApiError(msg) from e
            for ch in resp["channels"]:
                name = ch.get("name", "")
                if needle is None or needle in name.lower():
                    topic = ch.get("topic", {}).get("value", "")
                    out.append({"id": ch["id"], "name": name, "topic": topic})
            meta: dict[str, Any] = resp.get("response_metadata") or {}
            cursor = meta.get("next_cursor", "")
            if not cursor:
                break
        return out

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        """Return a permalink URL for a message."""
        try:
            resp = await self._web.chat_getPermalink(channel=channel_id, message_ts=message_ts)
        except _SdkSlackApiError as e:
            msg = f"Slack API error: {e.response['error']}"
            raise SlackApiError(msg) from e
        return str(resp["permalink"])

    async def resolve_users(self, user_ids: list[str]) -> dict[str, str]:
        """Map user ids to display names, caching results on the client."""
        for uid in user_ids:
            if not uid or uid in self._user_names:
                continue
            try:
                resp = await self._web.users_info(user=uid)
            except _SdkSlackApiError:
                self._user_names[uid] = uid
                continue
            profile = resp["user"].get("profile", {})
            self._user_names[uid] = (
                profile.get("display_name") or resp["user"].get("real_name") or uid
            )
        return {uid: self._user_names[uid] for uid in user_ids if uid}

    async def post_message(
        self, channel_id: str, text: str, thread_ts: str | None = None
    ) -> dict[str, Any]:
        """Post a message via chat.postMessage. The ONLY write path."""
        try:
            resp = await self._web.chat_postMessage(
                channel=channel_id, text=text, thread_ts=thread_ts
            )
        except _SdkSlackApiError as e:
            msg = f"Slack API error: {e.response['error']}"
            raise SlackApiError(msg) from e
        return {"ts": resp["ts"], "channel": resp["channel"]}


_slack_client: SlackClient | None = None


def get_slack_client() -> SlackClient:
    """Return the module-level SlackClient singleton, creating it from env if needed."""
    global _slack_client  # noqa: PLW0603
    if _slack_client is None:
        token = os.getenv("SLACK_USER_TOKEN")
        if not token:
            msg = (
                "Missing required environment variable: SLACK_USER_TOKEN\n"
                "Set SLACK_USER_TOKEN to your Slack user OAuth token (xoxp-...)."
            )
            raise ValueError(msg)
        _slack_client = SlackClient(token=token)
    return _slack_client


async def close_slack_client() -> None:
    """Close and clear the singleton (called on server shutdown)."""
    global _slack_client  # noqa: PLW0603
    if _slack_client is not None:
        await _slack_client.close()
        _slack_client = None
