# slack-mcp — Design

**Date:** 2026-07-17
**Status:** Approved for planning

## Purpose

An MCP server that lets Claude help with Jira-ticket and PR-related discussions
that happen on Slack. It can **search and read** messages and threads to gather
context about a ticket or PR, and can **send/reply** to messages only after a
strict, explicit confirmation step.

It is one of a set of Cloudera-specific MCP servers and follows the conventions
of the existing `jira-mcp` server (FastMCP, `uv`, `src/<pkg>/` layout, strict
ruff/mypy).

## Non-goals (YAGNI)

- No reading of DMs, private channels, or multi-person group DMs.
- No reactions, file uploads, message edits, deletes, pins, or channel
  management.
- No admin/enterprise APIs.
- No dedicated Jira/GitHub API integration. Searching Slack *by* a ticket key
  (`DSE-1234`) or PR URL is fully supported — the model passes it as the search
  query and Slack returns messages containing that string. What's out of scope
  is this server calling Jira/GitHub itself to enrich results or maintaining a
  ticket↔thread mapping; that belongs in `jira-mcp` / `github-mcp-server` or in
  how the model orchestrates the servers together. This server stays a thin,
  safe Slack accessor.

## Auth model

- **User OAuth token** (`xoxp-`), supplied via `SLACK_USER_TOKEN`.
- The server acts as the authenticated user. This is required because Slack's
  `search.messages` API only works with a user token; bot tokens cannot search.
- Consequence: the token can technically see everything the user can, so **all
  access restrictions are enforced in the server's tool/client code**, not by
  the token's scopes.
- Required Slack scopes: `search:read`, `channels:history`, `channels:read`,
  `users:read`, `chat:write`. (Public-channel scopes only — we deliberately do
  not request `groups:*`, `im:*`, or `mpim:*`.)

## Access guardrails

1. **Public channels only.** Reads are restricted to public channels. Channel
   resolution happens centrally in `client.py`; any channel whose type is a DM
   (`im`), private channel (`private_channel` / `is_private`), or group DM
   (`mpim`) raises a `ScopeError` before any data is read. Search results are
   filtered to public-channel matches only. This is enforced server-side and is
   not delegated to the model.
2. **Writes are gated by a server-issued token.** `send_message` is the only
   tool that posts, and it refuses to act without a valid, unexpired,
   single-use confirmation token that the server itself minted from a prior
   `draft_message` call. The model cannot fabricate a send.

## Architecture

Layout mirrors `jira-mcp`:

```
slack-mcp/
  pyproject.toml
  README.md
  setup.sh
  uv.lock
  src/slack_mcp_server/
    __init__.py
    __main__.py
    server.py       # entry point; argparse transport (stdio default); imports tools
    app.py          # FastMCP instance + lifespan that closes the Slack client
    client.py       # AsyncWebClient wrapper: auth, pagination, scope guard, caches
    tools.py        # @mcp.tool() registrations (side-effect import)
    confirm.py      # in-memory pending-draft store: token -> payload, TTL, single-use
    formatting.py   # Slack API objects -> readable dicts (resolve users, permalinks)
  tests/
    test_scope_guard.py
    test_confirm.py
    test_tools_read.py
    test_tools_write.py
```

### Components

- **`app.py`** — creates `mcp = FastMCP("slack-mcp", lifespan=...)`. Lifespan
  closes the shared Slack client on shutdown. Same shape as `jira-mcp/app.py`.

- **`client.py`** — wraps `slack_sdk.web.async_client.AsyncWebClient`.
  - Reads `SLACK_USER_TOKEN` from env; fails fast with a clear message if unset.
  - `AsyncWebClient` handles cursor pagination and 429 rate-limit retries.
  - `resolve_channel(channel)` — accepts a channel id or `#name`, returns the
    channel object, and raises `ScopeError` if it is not a public channel.
  - `is_public_channel(obj) -> bool` — the single source of truth for the guard.
  - User-name cache: `user_id -> display_name`, populated lazily via
    `users.info` / batched, to make output readable and cut API calls.
  - Helper to build/fetch permalinks (`chat.getPermalink`).

- **`formatting.py`** — pure functions turning raw Slack message dicts into
  compact, readable dicts: `{author, text, ts, permalink, channel}`; resolves
  user mentions and author ids to display names via the client cache. No I/O
  beyond what the client cache exposes; easy to unit-test.

- **`confirm.py`** — in-memory store for pending drafts.
  - `create_draft(payload) -> token` — random token (`secrets.token_urlsafe`),
    stores `payload` + expiry timestamp.
  - `consume(token) -> payload` — returns the payload and deletes it; raises if
    unknown or expired. Single-use.
  - TTL from `SLACK_DRAFT_TTL_SECONDS` (default 300).
  - Note: time-based expiry uses the standard clock; TTL is a soft safety net,
    single-use + preview are the primary guarantees.

- **`tools.py`** — thin tool functions that call the client, run results through
  `formatting.py`, and (for writes) go through `confirm.py`.

## Tools

### Read (public channels only)

- `search_messages(query: str, count: int = 20)` — `search.messages`; results
  filtered to public-channel matches; each item carries permalink, author,
  channel name, timestamp, and text. Intended queries: ticket keys
  (`DSE-1234`), PR URLs, free text.
- `read_thread(channel: str, thread_ts: str)` — root message + all replies via
  `conversations.replies`, author names resolved. Accepts a channel id/`#name`.
  (A permalink can be resolved to `channel`+`thread_ts` by the model or a small
  helper.)
- `read_channel_history(channel: str, limit: int = 30, around_ts: str | None = None)`
  — recent messages, or messages around a timestamp for context, via
  `conversations.history`.
- `list_channels(name_filter: str | None = None)` — public channels via
  `conversations.list` (types restricted to `public_channel`), optional
  substring filter on name.
- `resolve_users(user_ids: list[str])` — batch id -> display name, backed by the
  cache.

### Write (two-step, guarded)

- `draft_message(channel: str, text: str, thread_ts: str | None = None)` —
  validates the channel is public, renders an exact preview (target channel
  name, thread context if replying, and the full text), stores the payload, and
  returns `{preview, confirmation_token}`. **Does not post.**
- `send_message(confirmation_token: str)` — consumes the token from `confirm.py`
  (rejecting unknown/expired), posts via `chat.postMessage`, and returns the
  posted message's permalink. This is the only tool that writes to Slack.

## Data flow

**Reading about a ticket:**
`search_messages("PROJ-1234")` → pick a hit → `read_thread(channel, thread_ts)`
→ optionally `read_channel_history(..., around_ts=...)` for surrounding context.
All channel resolution passes through the public-only scope guard.

**Replying:**
`draft_message(channel, text, thread_ts)` → server returns rendered preview +
token → the human sees the preview and approves the `send_message` call →
`send_message(token)` posts and returns the permalink. Without a fresh valid
token, nothing posts.

## Error handling

- **Missing token env var:** fail fast at first client use with an actionable
  message naming `SLACK_USER_TOKEN`.
- **Scope violation:** `ScopeError` → returned to the model as a clear error
  ("channel X is not a public channel; this server only accesses public
  channels"). No partial data leaks.
- **Slack API errors:** surface `error` from the Slack response envelope
  (e.g. `channel_not_found`, `not_in_channel`, `ratelimited`) as readable tool
  errors; `AsyncWebClient` retries 429s.
- **Bad/expired confirmation token:** `send_message` returns a clear error
  instructing the caller to `draft_message` again. Never posts on a miss.

## Testing

pytest + `pytest-asyncio` with a mocked `AsyncWebClient` (no network):

- **`test_scope_guard`** — `resolve_channel` raises `ScopeError` for `im`,
  `mpim`, and private channels; passes for public; search results drop
  non-public hits.
- **`test_confirm`** — token round-trips; `consume` is single-use; expired
  tokens rejected; unknown tokens rejected.
- **`test_tools_read`** — `search_messages`/`read_thread` shape and user-name
  resolution/caching (cache hit avoids a second `users.info` call).
- **`test_tools_write`** — `draft_message` returns preview + token and does NOT
  call `chat.postMessage`; `send_message` with the token posts once and returns
  a permalink; `send_message` with a bad/expired token raises and does not post.

## Configuration summary

| Env var                   | Required | Default | Purpose                           |
| ------------------------- | -------- | ------- | --------------------------------- |
| `SLACK_USER_TOKEN`        | yes      | —       | User OAuth token (`xoxp-`)        |
| `SLACK_DRAFT_TTL_SECONDS` | no       | 300     | Draft confirmation-token lifetime |

## Dependencies

- `mcp>=1.9.0`
- `slack_sdk>=3.27.0`
- `pydantic>=2.0.0`
- dev: `pytest`, `pytest-asyncio`, `black`, `ruff`, `mypy` (same config as
  `jira-mcp`).
