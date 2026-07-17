"""MCP tool definitions for the Slack MCP server.

Includes read-only tools and write tools with two-step confirmation.
"""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from . import confirm, formatting
from .app import mcp
from .client import ScopeError, SlackApiError, get_slack_client

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


@mcp.tool(annotations=_READ_ONLY)
async def search_messages(query: str, count: int = 20) -> dict[str, Any]:
    """
    Search Slack messages in PUBLIC channels only.

    Use this to find discussions about a Jira ticket or PR by passing the ticket
    key (e.g. "DSE-1234"), a PR URL, or free-text keywords as the query. Results
    from DMs and private channels are never returned.

    Args:
        query: Search text — a ticket key, PR URL, or keywords.
        count: Max results (1-100, default 20).
    """
    try:
        validated = max(1, min(count, 100))
        client = get_slack_client()
        matches = await client.search_messages(query, validated)
        if not matches:
            return {"result": f"No messages found in public channels for query: {query}"}
        user_ids = formatting.collect_user_ids(matches)
        user_names = await client.resolve_users(user_ids)
        lines = [f"# Search results for `{query}`", f"{len(matches)} public-channel match(es)", ""]
        for m in matches:
            channel_name = m.get("channel", {}).get("name")
            lines.append(
                formatting.format_message(
                    m, user_names, channel_name=channel_name, permalink=m.get("permalink")
                )
            )
            lines.append("")
        return {"result": "\n".join(lines).rstrip()}
    except (ScopeError, SlackApiError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error searching messages: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def read_thread(channel: str, thread_ts: str) -> dict[str, Any]:
    """
    Read a full thread (root message + all replies) from a PUBLIC channel.

    Args:
        channel: Channel id (e.g. "C0123") or "#name". Must be a public channel.
        thread_ts: The thread's root timestamp (the `ts` of the first message).
    """
    try:
        client = get_slack_client()
        channel_obj = await client.resolve_channel(channel)
        messages = await client.conversations_replies(channel_obj["id"], thread_ts)
        if not messages:
            return {"result": "No messages found for that thread."}
        user_names = await client.resolve_users(formatting.collect_user_ids(messages))
        rendered = formatting.format_thread(
            messages, user_names, channel_name=channel_obj.get("name", channel)
        )
    except (ScopeError, SlackApiError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error reading thread: {e!s}"}
    else:
        return {"result": rendered}


@mcp.tool(annotations=_READ_ONLY)
async def read_channel_history(
    channel: str, limit: int = 30, around_ts: str | None = None
) -> dict[str, Any]:
    """
    Read recent messages from a PUBLIC channel, or messages around a timestamp.

    Args:
        channel: Channel id or "#name". Must be a public channel.
        limit: Number of messages (1-100, default 30).
        around_ts: Optional message timestamp; returns messages up to and
            including it, for context around a specific point.
    """
    try:
        validated = max(1, min(limit, 100))
        client = get_slack_client()
        channel_obj = await client.resolve_channel(channel)
        messages = await client.conversations_history(channel_obj["id"], validated, around_ts)
        if not messages:
            return {"result": "No messages found in that channel."}
        user_names = await client.resolve_users(formatting.collect_user_ids(messages))
        name = channel_obj.get("name", channel)
        blocks = [f"# Recent messages in #{name}", ""]
        for m in messages:
            blocks.append(formatting.format_message(m, user_names))
            blocks.append("")
        return {"result": "\n".join(blocks).rstrip()}
    except (ScopeError, SlackApiError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error reading channel history: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def list_channels(name_filter: str | None = None) -> dict[str, Any]:
    """
    List PUBLIC channels, optionally filtered by a name substring.

    Args:
        name_filter: Optional case-insensitive substring to match channel names.
    """
    try:
        client = get_slack_client()
        channels = await client.list_public_channels(name_filter)
        if not channels:
            return {"result": "No matching public channels found."}
        lines = ["# Public channels", ""]
        for ch in channels:
            topic = f" — {ch['topic']}" if ch.get("topic") else ""
            lines.append(f"- #{ch['name']} (`{ch['id']}`){topic}")
        return {"result": "\n".join(lines)}
    except SlackApiError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error listing channels: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def resolve_users(user_ids: list[str]) -> dict[str, Any]:
    """
    Resolve Slack user ids (e.g. "U0123") to display names.

    Args:
        user_ids: List of Slack user ids to resolve.
    """
    try:
        client = get_slack_client()
        names = await client.resolve_users(user_ids)
        if not names:
            return {"result": "No users resolved."}
        lines = [f"- {uid}: {name}" for uid, name in names.items()]
        return {"result": "\n".join(lines)}
    except SlackApiError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error resolving users: {e!s}"}


@mcp.tool()
async def draft_message(channel: str, text: str, thread_ts: str | None = None) -> dict[str, Any]:
    """
    Prepare a message for sending and return a preview + confirmation token.

    THIS DOES NOT SEND ANYTHING. It validates the target is a public channel,
    renders exactly what would be posted, and returns a one-time
    `confirmation_token`. To actually post, the user must review this preview and
    then call `send_message(confirmation_token=...)`. Always show the user this
    preview and get their explicit approval before calling send_message.

    Args:
        channel: Channel id or "#name". Must be a public channel.
        text: The exact message text to post.
        thread_ts: Optional thread root timestamp to reply in a thread.
    """
    try:
        client = get_slack_client()
        channel_obj = await client.resolve_channel(channel)
        payload = confirm.DraftPayload(
            channel_id=channel_obj["id"],
            channel_name=channel_obj.get("name", channel),
            text=text,
            thread_ts=thread_ts,
        )
        token = confirm.drafts.create(payload)
        target = f"#{payload.channel_name}"
        if thread_ts:
            target += f" (reply in thread {thread_ts})"
        preview = [
            "# Draft — NOT yet sent",
            f"**To:** {target}",
            "**Message:**",
            payload.text,
            "",
            f"**confirmation_token:** `{token}`",
            "",
            "Review the above. To send, call " f'`send_message(confirmation_token="{token}")`.',
        ]
        return {"result": "\n".join(preview)}
    except (ScopeError, SlackApiError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error drafting message: {e!s}"}


@mcp.tool()
async def send_message(confirmation_token: str) -> dict[str, Any]:
    """
    Send a previously drafted message. Requires a valid confirmation_token from
    draft_message. This is the ONLY tool that posts to Slack.

    Only call this after the user has reviewed the draft_message preview and
    explicitly approved sending.

    Args:
        confirmation_token: The one-time token returned by draft_message.
    """
    try:
        payload = confirm.drafts.consume(confirmation_token)
    except confirm.DraftError as e:
        return {"error": str(e)}
    try:
        client = get_slack_client()
        posted = await client.post_message(
            payload.channel_id, payload.text, thread_ts=payload.thread_ts
        )
        permalink = await client.get_permalink(posted["channel"], posted["ts"])
    except SlackApiError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error sending message: {e!s}"}
    else:
        return {"result": f"Message sent to #{payload.channel_name}.\nPermalink: {permalink}"}
