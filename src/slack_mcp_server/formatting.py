"""Pure helpers that turn raw Slack message dicts into readable markdown.

No I/O: user display names are resolved by the client and passed in as a map.
"""

from __future__ import annotations

import re
from typing import Any

_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")


def collect_user_ids(messages: list[dict[str, Any]]) -> list[str]:
    """Return the unique, non-empty `user` ids across messages, preserving order."""
    seen: dict[str, None] = {}
    for msg in messages:
        uid = msg.get("user")
        if uid and uid not in seen:
            seen[uid] = None
    return list(seen)


def substitute_mentions(text: str, user_names: dict[str, str]) -> str:
    """Replace `<@U123>` mentions with `@display_name` when the name is known."""

    def repl(match: re.Match[str]) -> str:
        uid = match.group(1)
        name = user_names.get(uid)
        return f"@{name}" if name else match.group(0)

    return _MENTION_RE.sub(repl, text)


def _author(msg: dict[str, Any], user_names: dict[str, str]) -> str:
    uid = msg.get("user", "")
    return user_names.get(uid) or msg.get("username") or uid or "unknown"


def format_message(
    msg: dict[str, Any],
    user_names: dict[str, str],
    *,
    channel_name: str | None = None,
    permalink: str | None = None,
) -> str:
    """Render a single message as a readable markdown block."""
    author = _author(msg, user_names)
    text = substitute_mentions(msg.get("text", ""), user_names)
    ts = msg.get("ts", "")
    lines = [f"**{author}** ({ts}):", text]
    if channel_name:
        lines.insert(0, f"#{channel_name}")
    if permalink:
        lines.append(f"<{permalink}>")
    return "\n".join(lines)


def format_thread(
    messages: list[dict[str, Any]],
    user_names: dict[str, str],
    *,
    channel_name: str,
) -> str:
    """Render a full thread (root + replies) in order."""
    blocks = [f"# Thread in #{channel_name}", ""]
    for msg in messages:
        blocks.append(format_message(msg, user_names))
        blocks.append("")
    return "\n".join(blocks).rstrip()
