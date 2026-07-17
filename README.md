# Slack MCP Server

Search and read public-channel Slack discussions about Jira tickets and PRs, and
send/reply to messages only after an explicit two-step confirmation.

## What it can and can't do

- **Reads public channels only.** DMs, private channels, and group DMs are
  refused by a server-side guard — even though the user token could see them.
- **Search** uses Slack's `search.messages`, which requires a **user token**.
- **Sending is two-step:** `draft_message` returns a preview + one-time token;
  nothing posts until you call `send_message` with that token.

## Slack app setup

1. Create an app at https://api.slack.com/apps.
2. Under **OAuth & Permissions → User Token Scopes**, add:
   `search:read`, `channels:history`, `channels:read`, `users:read`, `chat:write`.
3. Install the app to your workspace and copy the **User OAuth Token** (`xoxp-...`).

## Configuration

```bash
export SLACK_USER_TOKEN="xoxp-..."          # required
export SLACK_DRAFT_TTL_SECONDS=300           # optional, default 300
```

## Run

```bash
uv sync
uv run slack-mcp
```

## MCP client config

```json
{
  "mcpServers": {
    "slack": {
      "command": "uv",
      "args": ["run", "slack-mcp"],
      "cwd": "/absolute/path/to/slack-mcp",
      "env": { "SLACK_USER_TOKEN": "xoxp-..." }
    }
  }
}
```

## Tools

- `search_messages(query, count=20)` — find messages in public channels.
- `read_thread(channel, thread_ts)` — full thread with resolved names.
- `read_channel_history(channel, limit=30, around_ts=None)` — recent/context.
- `list_channels(name_filter=None)` — public channels.
- `resolve_users(user_ids)` — ids → display names.
- `draft_message(channel, text, thread_ts=None)` — preview + token; does NOT send.
- `send_message(confirmation_token)` — sends the drafted message (only write path).
