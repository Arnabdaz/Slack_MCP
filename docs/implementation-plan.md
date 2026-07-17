# slack-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Slack MCP server that can search and read public-channel messages/threads for Jira-ticket and PR discussions, and can send/reply only after a strict two-step confirmation.

**Architecture:** FastMCP server mirroring the existing `jira-mcp` layout. A `client.py` wraps `slack_sdk`'s `AsyncWebClient` and centralizes a public-channel-only scope guard + a user-name cache. `confirm.py` holds an in-memory single-use draft store. Read tools return formatted, user-name-resolved dicts; the only write path (`send_message`) requires a server-issued token minted by `draft_message`.

**Tech Stack:** Python 3.10+, `mcp` (FastMCP), `slack_sdk` (AsyncWebClient), `pydantic`, `uv`, `pytest`/`pytest-asyncio`. Lint/type: `ruff`, `black`, `mypy --strict` (same config as `jira-mcp`).

**Spec:** `docs/design.md`

## Global Constraints

- Package name: `slack-mcp`; Python package dir: `src/slack_mcp_server/`; console script: `slack-mcp = "slack_mcp_server.server:main"`.
- `requires-python = ">=3.10"`. Every module starts with `from __future__ import annotations`.
- Dependencies: `mcp>=1.9.0`, `slack_sdk>=3.27.0`, `pydantic>=2.0.0`. Dev: `pytest>=7.0.0`, `pytest-asyncio>=0.21.0`, `black>=23.0.0`, `ruff>=0.1.0`, `mypy>=1.0.0`.
- Copy the `[tool.ruff]`, `[tool.black]`, `[tool.mypy]`, and `[tool.pytest.ini_options]` blocks verbatim from `jira-mcp/pyproject.toml` (asyncio_mode = "auto", strict mypy, ruff line-length 100).
- Config env vars: `SLACK_USER_TOKEN` (required, `xoxp-`), `SLACK_DRAFT_TTL_SECONDS` (optional, default 300).
- **Tool return convention** (matches `jira-mcp`): every `@mcp.tool` returns `dict[str, Any]`, either `{"result": <str>}` on success or `{"error": <str>}` on failure. Read tools are decorated `@mcp.tool(annotations=_READ_ONLY)` where `_READ_ONLY = ToolAnnotations(readOnlyHint=True)`.
- **Access guardrail (non-negotiable):** every channel touched by any read or write tool passes through `SlackClient.resolve_channel`, which raises `ScopeError` for anything that is not a public channel (DM `is_im`, group DM `is_mpim`, private `is_private`). Search results are filtered to public matches. This is enforced in `client.py`, never delegated to the model.
- **Write guardrail (non-negotiable):** `send_message` is the ONLY tool that calls `chat.postMessage`. It posts only when given a valid, unexpired, single-use token minted by `draft_message`. `draft_message` never posts.
- All commits happen inside the `slack-mcp/` git repo created in Task 1. Run every command from the `slack-mcp/` directory.

---

### Task 1: Project scaffolding

**Files:**
- Create: `slack-mcp/pyproject.toml`
- Create: `slack-mcp/src/slack_mcp_server/__init__.py`
- Create: `slack-mcp/src/slack_mcp_server/__main__.py`
- Create: `slack-mcp/src/slack_mcp_server/app.py`
- Create: `slack-mcp/src/slack_mcp_server/server.py`
- Create: `slack-mcp/.gitignore`
- Test: `slack-mcp/tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `slack_mcp_server.app.mcp` (a `FastMCP` instance named `"slack-mcp"`); `slack_mcp_server.server.main() -> None`.

- [ ] **Step 1: Create the directory and init git**

```bash
mkdir -p slack-mcp/src/slack_mcp_server slack-mcp/tests
cd slack-mcp
git init
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "slack-mcp"
version = "0.1.0"
description = "MCP server for Slack — search/read public-channel discussions and send messages with strict confirmation"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
keywords = ["mcp", "slack", "model-context-protocol"]

dependencies = [
    "mcp>=1.9.0",
    "slack_sdk>=3.27.0",
    "pydantic>=2.0.0",
]

[dependency-groups]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
slack-mcp = "slack_mcp_server.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/slack_mcp_server"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "ANN", "S", "B", "C4", "DTZ", "T10", "EM", "G", "PIE", "PT", "RET", "SIM", "ARG", "PTH", "PD", "PGH", "PL", "TRY", "NPY", "PERF", "RUF"]
ignore = ["ANN401", "S101", "PLR0911", "PLR0912", "PLR0913", "PLR0915"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "S105", "S106", "N802", "PLR2004", "PLC0415"]
"src/slack_mcp_server/tools.py" = ["E501"]

[tool.black]
line-length = 100
target-version = ["py310"]

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-p no:anyio"
filterwarnings = [
    "ignore::pytest.PytestAssertRewriteWarning",
    "ignore:Module already imported so cannot be rewritten.*anyio:pytest.PytestAssertRewriteWarning"
]
```

- [ ] **Step 3: Write `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
*.egg-info/
dist/
```

- [ ] **Step 4: Write `src/slack_mcp_server/app.py`**

```python
"""FastMCP application instance — imported by both server.py and tools.py."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP


@contextlib.asynccontextmanager
async def _lifespan(app: FastMCP) -> AsyncIterator[None]:  # noqa: ARG001
    """Close the Slack HTTP client on server shutdown."""
    yield
    from .client import close_slack_client  # noqa: PLC0415

    await close_slack_client()


mcp = FastMCP("slack-mcp", lifespan=_lifespan)
```

- [ ] **Step 5: Write `src/slack_mcp_server/server.py`**

```python
"""Slack MCP Server — entry point."""

from __future__ import annotations

import argparse
import logging

from .app import mcp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import tools module to trigger @mcp.tool() registration via side effects
from . import tools  # noqa: E402, F401


def main() -> None:
    """Parse CLI arguments and start the MCP server."""
    parser = argparse.ArgumentParser(description="Slack MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mechanism (default: stdio)",
    )
    args = parser.parse_args()
    logger.info("Starting Slack MCP Server with %s transport", args.transport)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Write `src/slack_mcp_server/__init__.py`**

```python
"""Slack MCP Server — a Model Context Protocol server for Slack discussions."""

from __future__ import annotations

__version__ = "0.1.0"

from .server import main

__all__ = ["main"]
```

- [ ] **Step 7: Write `src/slack_mcp_server/__main__.py`**

```python
"""Allow running the package directly with `python -m slack_mcp_server`."""

from __future__ import annotations

from .server import main

main()
```

> NOTE: `server.py` imports `from . import tools`, so a `tools.py` must exist for the package to import. Create a temporary stub now; Tasks 6–7 fill it in.

- [ ] **Step 8: Write a temporary `src/slack_mcp_server/tools.py` stub**

```python
"""MCP tool definitions (populated in later tasks)."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .app import mcp  # noqa: F401

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
```

- [ ] **Step 9: Write the smoke test `tests/test_smoke.py`**

```python
"""Smoke test: the package imports and exposes a configured FastMCP instance."""

from __future__ import annotations


def test_mcp_instance_name() -> None:
    from slack_mcp_server.app import mcp

    assert mcp.name == "slack-mcp"


def test_main_is_callable() -> None:
    from slack_mcp_server import main

    assert callable(main)
```

- [ ] **Step 10: Sync dependencies**

Run: `uv sync`
Expected: creates `.venv`, installs `mcp`, `slack_sdk`, `pydantic`, and dev tools; writes `uv.lock`.

- [ ] **Step 11: Run the smoke test to verify it passes**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "chore: scaffold slack-mcp package"
```

---

### Task 2: In-memory draft confirmation store (`confirm.py`)

**Files:**
- Create: `slack-mcp/src/slack_mcp_server/confirm.py`
- Test: `slack-mcp/tests/test_confirm.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class DraftPayload(pydantic.BaseModel)` with fields `channel_id: str`, `channel_name: str`, `text: str`, `thread_ts: str | None = None`.
  - `class DraftStore` with:
    - `__init__(self, ttl_seconds: int = 300, *, clock: Callable[[], float] = time.monotonic) -> None`
    - `create(self, payload: DraftPayload) -> str` — returns a URL-safe token.
    - `consume(self, token: str) -> DraftPayload` — returns payload and deletes it; raises `DraftError` if unknown or expired.
  - `class DraftError(Exception)`.
  - Module-level singleton `drafts: DraftStore` built from `SLACK_DRAFT_TTL_SECONDS` (default 300).

- [ ] **Step 1: Write the failing test `tests/test_confirm.py`**

```python
"""Tests for the in-memory draft confirmation store."""

from __future__ import annotations

import pytest

from slack_mcp_server.confirm import DraftError, DraftPayload, DraftStore


def _payload(text: str = "hello") -> DraftPayload:
    return DraftPayload(channel_id="C123", channel_name="eng-prs", text=text)


class TestDraftStore:
    def test_create_returns_nonempty_token(self) -> None:
        store = DraftStore(ttl_seconds=300, clock=lambda: 0.0)
        token = store.create(_payload())
        assert isinstance(token, str)
        assert len(token) >= 16

    def test_consume_returns_payload(self) -> None:
        store = DraftStore(ttl_seconds=300, clock=lambda: 0.0)
        token = store.create(_payload("hi there"))
        payload = store.consume(token)
        assert payload.text == "hi there"
        assert payload.channel_id == "C123"

    def test_consume_is_single_use(self) -> None:
        store = DraftStore(ttl_seconds=300, clock=lambda: 0.0)
        token = store.create(_payload())
        store.consume(token)
        with pytest.raises(DraftError):
            store.consume(token)

    def test_unknown_token_raises(self) -> None:
        store = DraftStore(ttl_seconds=300, clock=lambda: 0.0)
        with pytest.raises(DraftError):
            store.consume("does-not-exist")

    def test_expired_token_raises(self) -> None:
        now = {"t": 0.0}
        store = DraftStore(ttl_seconds=300, clock=lambda: now["t"])
        token = store.create(_payload())
        now["t"] = 301.0
        with pytest.raises(DraftError):
            store.consume(token)

    def test_tokens_are_unique(self) -> None:
        store = DraftStore(ttl_seconds=300, clock=lambda: 0.0)
        tokens = {store.create(_payload()) for _ in range(50)}
        assert len(tokens) == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_confirm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'slack_mcp_server.confirm'`.

- [ ] **Step 3: Write `src/slack_mcp_server/confirm.py`**

```python
"""In-memory, single-use store for pending message drafts.

A draft is created by `draft_message` and can only be sent by `send_message`
presenting the exact token minted here. Tokens are single-use and expire.
"""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable

from pydantic import BaseModel


class DraftError(Exception):
    """Raised when a confirmation token is unknown or expired."""


class DraftPayload(BaseModel):
    """The exact content a confirmed send will post."""

    channel_id: str
    channel_name: str
    text: str
    thread_ts: str | None = None


class _Entry(BaseModel):
    payload: DraftPayload
    expires_at: float


class DraftStore:
    """Holds pending drafts keyed by a one-time token."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _Entry] = {}

    def create(self, payload: DraftPayload) -> str:
        """Store a draft and return its one-time confirmation token."""
        token = secrets.token_urlsafe(24)
        self._entries[token] = _Entry(
            payload=payload,
            expires_at=self._clock() + self._ttl,
        )
        return token

    def consume(self, token: str) -> DraftPayload:
        """Return and remove the draft for `token`; raise DraftError if invalid."""
        entry = self._entries.pop(token, None)
        if entry is None:
            msg = "Unknown or already-used confirmation token. Call draft_message again."
            raise DraftError(msg)
        if self._clock() > entry.expires_at:
            msg = "Confirmation token expired. Call draft_message again to get a fresh one."
            raise DraftError(msg)
        return entry.payload


def _build_store() -> DraftStore:
    ttl = int(os.getenv("SLACK_DRAFT_TTL_SECONDS", "300"))
    return DraftStore(ttl_seconds=ttl)


drafts = _build_store()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_confirm.py -v`
Expected: 6 passed.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check src/slack_mcp_server/confirm.py && uv run mypy src/slack_mcp_server/confirm.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add in-memory single-use draft confirmation store"
```

---

### Task 3: Slack client — config, singleton, and public-channel scope guard (`client.py`)

**Files:**
- Create: `slack-mcp/src/slack_mcp_server/client.py`
- Test: `slack-mcp/tests/test_scope_guard.py`

**Interfaces:**
- Consumes: nothing.
- Produces (this task adds config + guard; Task 4 adds API methods to the same class/file):
  - `class ScopeError(Exception)`.
  - `class SlackApiError(Exception)` with `__init__(self, message: str)`.
  - `def is_public_channel(channel_obj: dict[str, Any]) -> bool` — `True` only when the object is a public channel (`is_channel` true, and none of `is_private`, `is_im`, `is_mpim`, `is_group`).
  - `class SlackClient`:
    - `__init__(self, token: str, *, web_client: Any | None = None) -> None` — builds an `AsyncWebClient` with a rate-limit retry handler unless `web_client` is injected (for tests).
    - `async def resolve_channel(self, channel: str) -> dict[str, Any]` — accepts a channel id or `#name`/`name`, returns the channel object via `conversations.info` (resolving name→id through `conversations.list` first), and raises `ScopeError` if `is_public_channel` is false.
    - `async def close(self) -> None`.
    - `self._web: AsyncWebClient` (the underlying client, used by Task 4 methods).
  - `def get_slack_client() -> SlackClient` — module singleton from `SLACK_USER_TOKEN`; raises `ValueError` with an actionable message if unset.
  - `async def close_slack_client() -> None` — closes and clears the singleton (used by `app.py` lifespan).

- [ ] **Step 1: Write the failing test `tests/test_scope_guard.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scope_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'slack_mcp_server.client'`.

- [ ] **Step 3: Write `src/slack_mcp_server/client.py` (config + guard portion)**

```python
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
                raise SlackApiError(f"Slack API error: {e.response['error']}") from e
            for ch in resp["channels"]:
                if ch.get("name") == name:
                    return str(ch["id"])
            cursor = resp.get("response_metadata", {}).get("next_cursor", "")
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
            raise SlackApiError(f"Slack API error: {e.response['error']}") from e
        obj: dict[str, Any] = resp["channel"]
        if not is_public_channel(obj):
            msg = (
                f"Channel '{channel}' is not a public channel. "
                "This server only accesses public channels."
            )
            raise ScopeError(msg)
        return obj


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scope_guard.py -v`
Expected: all passed (11 tests).

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check src/slack_mcp_server/client.py && uv run mypy src/slack_mcp_server/client.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add Slack client config, singleton, and public-channel scope guard"
```

---

### Task 4: Slack client — API methods and user-name cache (`client.py`)

**Files:**
- Modify: `slack-mcp/src/slack_mcp_server/client.py` (add methods to `SlackClient`)
- Test: `slack-mcp/tests/test_client_api.py`

**Interfaces:**
- Consumes: `SlackClient`, `ScopeError`, `SlackApiError`, `is_public_channel` from Task 3.
- Produces (new methods on `SlackClient`; all raise `SlackApiError` on a Slack error response):
  - `async def search_messages(self, query: str, count: int = 20) -> list[dict[str, Any]]` — calls `search.messages`; returns only matches whose `channel` object is public (via `is_public_channel`). Each returned item is the raw Slack match dict.
  - `async def conversations_replies(self, channel_id: str, thread_ts: str) -> list[dict[str, Any]]` — returns the messages list (root + replies).
  - `async def conversations_history(self, channel_id: str, limit: int = 30, around_ts: str | None = None) -> list[dict[str, Any]]` — when `around_ts` is given, fetch a window centered on it using `latest=around_ts, inclusive=True`; else most recent `limit`.
  - `async def list_public_channels(self, name_filter: str | None = None) -> list[dict[str, Any]]` — paginated `conversations.list(types="public_channel")`; each item `{"id", "name", "topic"}`; optional case-insensitive substring filter on name.
  - `async def get_permalink(self, channel_id: str, message_ts: str) -> str` — `chat.getPermalink`.
  - `async def resolve_users(self, user_ids: list[str]) -> dict[str, str]` — id→display name, cached on `self._user_names`; only calls `users.info` for ids not already cached; empty/`None` ids skipped.
  - `async def post_message(self, channel_id: str, text: str, thread_ts: str | None = None) -> dict[str, Any]` — `chat.postMessage`; returns `{"ts", "channel"}`.

- [ ] **Step 1: Write the failing test `tests/test_client_api.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client_api.py -v`
Expected: FAIL — `AttributeError: 'SlackClient' object has no attribute 'search_messages'`.

- [ ] **Step 3: Add the API methods to `SlackClient` in `client.py`**

Add these imports if not already present (top of file): `from typing import Any` is already there. Insert the following methods into the `SlackClient` class (e.g. after `resolve_channel`):

```python
    async def search_messages(self, query: str, count: int = 20) -> list[dict[str, Any]]:
        """Search messages (search.messages); return only public-channel matches."""
        try:
            resp = await self._web.search_messages(query=query, count=count)
        except _SdkSlackApiError as e:
            raise SlackApiError(f"Slack API error: {e.response['error']}") from e
        matches = resp.get("messages", {}).get("matches", [])
        return [m for m in matches if is_public_channel(m.get("channel", {}))]

    async def conversations_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        """Return a thread's messages (root + replies)."""
        try:
            resp = await self._web.conversations_replies(channel=channel_id, ts=thread_ts)
        except _SdkSlackApiError as e:
            raise SlackApiError(f"Slack API error: {e.response['error']}") from e
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
            raise SlackApiError(f"Slack API error: {e.response['error']}") from e
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
                raise SlackApiError(f"Slack API error: {e.response['error']}") from e
            for ch in resp["channels"]:
                name = ch.get("name", "")
                if needle is None or needle in name.lower():
                    out.append(
                        {"id": ch["id"], "name": name, "topic": ch.get("topic", {}).get("value", "")}
                    )
            cursor = resp.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return out

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        """Return a permalink URL for a message."""
        try:
            resp = await self._web.chat_getPermalink(channel=channel_id, message_ts=message_ts)
        except _SdkSlackApiError as e:
            raise SlackApiError(f"Slack API error: {e.response['error']}") from e
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
            raise SlackApiError(f"Slack API error: {e.response['error']}") from e
        return {"ts": resp["ts"], "channel": resp["channel"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_client_api.py -v`
Expected: all passed (5 tests).

- [ ] **Step 5: Lint and type-check, run full suite**

Run: `uv run ruff check src/ && uv run mypy src/ && uv run pytest -q`
Expected: no lint/type errors; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add Slack client API methods and user-name cache"
```

---

### Task 5: Message formatting helpers (`formatting.py`)

**Files:**
- Create: `slack-mcp/src/slack_mcp_server/formatting.py`
- Test: `slack-mcp/tests/test_formatting.py`

**Interfaces:**
- Consumes: nothing (pure functions; user names are passed in, not fetched).
- Produces:
  - `def collect_user_ids(messages: list[dict[str, Any]]) -> list[str]` — unique `user` ids present across messages (skips empty).
  - `def substitute_mentions(text: str, user_names: dict[str, str]) -> str` — replaces `<@U123>` with `@display_name` when known, else leaves the raw token.
  - `def format_message(msg: dict[str, Any], user_names: dict[str, str], *, channel_name: str | None = None, permalink: str | None = None) -> str` — one readable markdown block: `**author** (ts): text`, with mentions substituted, plus channel/permalink lines when provided.
  - `def format_thread(messages: list[dict[str, Any]], user_names: dict[str, str], *, channel_name: str) -> str` — root + replies rendered in order.

- [ ] **Step 1: Write the failing test `tests/test_formatting.py`**

```python
"""Tests for pure message-formatting helpers."""

from __future__ import annotations

from typing import Any

from slack_mcp_server.formatting import (
    collect_user_ids,
    format_message,
    format_thread,
    substitute_mentions,
)


def _msg(user: str, text: str, ts: str = "1.0") -> dict[str, Any]:
    return {"user": user, "text": text, "ts": ts}


class TestCollectUserIds:
    def test_unique_and_skips_empty(self) -> None:
        msgs = [_msg("U1", "a"), _msg("U2", "b"), _msg("U1", "c"), {"text": "no user"}]
        assert sorted(collect_user_ids(msgs)) == ["U1", "U2"]


class TestSubstituteMentions:
    def test_known_mention_replaced(self) -> None:
        out = substitute_mentions("hey <@U1> look", {"U1": "alice"})
        assert out == "hey @alice look"

    def test_unknown_mention_left_as_is(self) -> None:
        out = substitute_mentions("hey <@U9>", {})
        assert "<@U9>" in out


class TestFormatMessage:
    def test_includes_author_and_text(self) -> None:
        out = format_message(_msg("U1", "hello <@U2>"), {"U1": "alice", "U2": "bob"})
        assert "alice" in out
        assert "hello @bob" in out

    def test_includes_permalink_when_given(self) -> None:
        out = format_message(_msg("U1", "hi"), {"U1": "alice"}, permalink="https://x/p/1")
        assert "https://x/p/1" in out


class TestFormatThread:
    def test_renders_all_messages_in_order(self) -> None:
        msgs = [_msg("U1", "root", "1.0"), _msg("U2", "reply", "2.0")]
        out = format_thread(msgs, {"U1": "alice", "U2": "bob"}, channel_name="eng")
        assert out.index("root") < out.index("reply")
        assert "alice" in out and "bob" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'slack_mcp_server.formatting'`.

- [ ] **Step 3: Write `src/slack_mcp_server/formatting.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: all passed (6 tests).

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check src/slack_mcp_server/formatting.py && uv run mypy src/slack_mcp_server/formatting.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add pure message-formatting helpers"
```

---

### Task 6: Read tools (`tools.py`)

**Files:**
- Modify: `slack-mcp/src/slack_mcp_server/tools.py` (replace the Task 1 stub)
- Test: `slack-mcp/tests/test_tools_read.py`

**Interfaces:**
- Consumes: `get_slack_client` (`client.py`), `ScopeError`, `SlackApiError`; `formatting` helpers; `mcp`, `_READ_ONLY`.
- Produces the read tools, each returning `dict[str, Any]` (`{"result": str}` or `{"error": str}`):
  - `search_messages(query: str, count: int = 20)`
  - `read_thread(channel: str, thread_ts: str)`
  - `read_channel_history(channel: str, limit: int = 30, around_ts: str | None = None)`
  - `list_channels(name_filter: str | None = None)`
  - `resolve_users(user_ids: list[str])`
- Tests patch `slack_mcp_server.tools.get_slack_client` with a `MagicMock` whose async methods are `AsyncMock`s (same pattern as `jira-mcp/tests/test_tools.py`).

- [ ] **Step 1: Write the failing test `tests/test_tools_read.py`**

```python
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
                {"ts": "1.0", "text": "DSE-1 is fixed", "user": "U1",
                 "channel": {"id": "C1", "name": "eng"}, "permalink": "https://x/p/1"},
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
            return_value=[{"user": "U1", "text": "root", "ts": "1.0"},
                          {"user": "U2", "text": "reply", "ts": "2.0"}]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools_read.py -v`
Expected: FAIL — `ImportError: cannot import name 'search_messages' from 'slack_mcp_server.tools'`.

- [ ] **Step 3: Replace `src/slack_mcp_server/tools.py` with the read-tool implementation**

```python
"""MCP tool definitions for Slack read operations.

Write tools (draft_message/send_message) are added in a later task.
"""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from . import formatting
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
    except Exception as e:  # noqa: BLE001
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
        return {"result": rendered}
    except (ScopeError, SlackApiError) as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Error reading thread: {e!s}"}


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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
        return {"error": f"Error resolving users: {e!s}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools_read.py -v`
Expected: all passed.

- [ ] **Step 5: Lint, type-check, full suite**

Run: `uv run ruff check src/ && uv run mypy src/ && uv run pytest -q`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add Slack read tools (search, thread, history, channels, users)"
```

---

### Task 7: Write tools with two-step confirmation (`tools.py`)

**Files:**
- Modify: `slack-mcp/src/slack_mcp_server/tools.py` (add write tools)
- Test: `slack-mcp/tests/test_tools_write.py`

**Interfaces:**
- Consumes: `get_slack_client`; `confirm.drafts`, `confirm.DraftPayload`, `confirm.DraftError`; `mcp`.
- Produces:
  - `draft_message(channel: str, text: str, thread_ts: str | None = None) -> dict[str, Any]` — validates the channel is public (via `resolve_channel`), stores a `DraftPayload` in `confirm.drafts`, and returns `{"result": <preview text incl. the confirmation_token>}`. Does NOT post. The preview shows target channel, thread context, the full text, and the token, plus an instruction to call `send_message(confirmation_token=...)`.
  - `send_message(confirmation_token: str) -> dict[str, Any]` — consumes the token from `confirm.drafts` (raising `DraftError` if invalid/expired), posts via `client.post_message`, returns `{"result": <permalink + confirmation>}`. Only tool that posts.
- Note: write tools are NOT decorated with `_READ_ONLY`.

- [ ] **Step 1: Write the failing test `tests/test_tools_write.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools_write.py -v`
Expected: FAIL — `ImportError: cannot import name 'draft_message' from 'slack_mcp_server.tools'`.

- [ ] **Step 3: Add write tools to `tools.py`**

Add the import near the top (below the existing imports):

```python
from . import confirm
```

Append the two write tools at the end of the file:

```python
@mcp.tool()
async def draft_message(
    channel: str, text: str, thread_ts: str | None = None
) -> dict[str, Any]:
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
            "Review the above. To send, call "
            f"`send_message(confirmation_token=\"{token}\")`.",
        ]
        return {"result": "\n".join(preview)}
    except (ScopeError, SlackApiError) as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001
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
        return {
            "result": f"Message sent to #{payload.channel_name}.\nPermalink: {permalink}"
        }
    except SlackApiError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Error sending message: {e!s}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools_write.py -v`
Expected: all passed.

- [ ] **Step 5: Lint, type-check, full suite**

Run: `uv run ruff check src/ && uv run mypy src/ && uv run pytest -q`
Expected: clean; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add two-step draft/send write tools with confirmation guard"
```

---

### Task 8: README, setup script, and manual verification

**Files:**
- Create: `slack-mcp/README.md`
- Create: `slack-mcp/setup.sh`

**Interfaces:**
- Consumes: everything above.
- Produces: docs + a manual smoke check. No automated test (documentation task); verification is running the server and listing tools.

- [ ] **Step 1: Write `README.md`**

Include: what the server does; the required Slack app setup (create an app at api.slack.com/apps, add **User Token Scopes**: `search:read`, `channels:history`, `channels:read`, `users:read`, `chat:write`; install to workspace; copy the User OAuth Token `xoxp-...`); env vars (`SLACK_USER_TOKEN`, optional `SLACK_DRAFT_TTL_SECONDS`); how the public-channel-only guard works; the two-step draft→send confirmation flow; and an MCP client config snippet:

````markdown
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
````

- [ ] **Step 2: Write `setup.sh`**

```bash
#!/bin/bash
# Setup script for Slack MCP Server (using uv)

echo "🚀 Setting up Slack MCP Server with uv..."

if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "📥 Installing dependencies with uv..."
uv sync

echo "✅ Setup complete!"
echo ""
echo "1. Create a Slack app and add User Token Scopes:"
echo "   search:read, channels:history, channels:read, users:read, chat:write"
echo "2. Export your user token:"
echo "   export SLACK_USER_TOKEN='xoxp-...'"
echo "3. Run the server:"
echo "   uv run slack-mcp"
```

- [ ] **Step 3: Make setup.sh executable**

Run: `chmod +x setup.sh`

- [ ] **Step 4: Manual verification — server boots and registers all 7 tools**

Run:
```bash
SLACK_USER_TOKEN=xoxp-dummy uv run python -c "
import asyncio
from slack_mcp_server import server  # triggers tool registration
from slack_mcp_server.app import mcp

async def main():
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    print(names)
    expected = ['draft_message','list_channels','read_channel_history','read_thread','resolve_users','search_messages','send_message']
    assert names == expected, names
    print('OK: all 7 tools registered')

asyncio.run(main())
"
```
Expected: prints the 7 tool names and `OK: all 7 tools registered`. (A dummy token is fine — no network call happens during registration/listing.)

- [ ] **Step 5: Full quality gate**

Run: `uv run ruff check . && uv run black --check . && uv run mypy src/ && uv run pytest -q`
Expected: all clean; every test passes.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: add README and setup script; verify tool registration"
```

---

## Self-Review

**Spec coverage:**
- User-token auth model → Task 3 (`get_slack_client`, `SLACK_USER_TOKEN`) + README setup (Task 8). ✔
- Public-channel-only read guard → Task 3 (`is_public_channel`, `resolve_channel`), search filtering Task 4, enforced in every read/write tool Tasks 6–7. ✔
- Two-step confirmed writes → Task 2 (store) + Task 7 (`draft_message`/`send_message`). ✔
- Tools: search / read_thread / channel history / list_channels / resolve_users → Task 6; draft/send → Task 7. ✔
- User-name resolution + caching → Task 4 (`resolve_users`) + Task 5 (`collect_user_ids`, `substitute_mentions`). ✔
- Permalinks → Task 4 (`get_permalink`), used in search output (Task 6) and send confirmation (Task 7). ✔
- Error handling (missing token, scope violation, Slack API errors, bad/expired token) → Tasks 3, 6, 7. ✔
- Config (`SLACK_USER_TOKEN`, `SLACK_DRAFT_TTL_SECONDS`) → Tasks 2, 3, 8. ✔
- Testing (scope guard, confirm, read tools, write tools) → Tasks 2–7. ✔
- Layout mirrors jira-mcp → Task 1. ✔

**Placeholder scan:** No TBD/TODO; every code step contains complete code; the Task 1 `tools.py` stub is explicitly temporary and fully replaced in Task 6.

**Type consistency:** `DraftPayload` fields (`channel_id`, `channel_name`, `text`, `thread_ts`) are consistent across Tasks 2/7. `resolve_channel` returns a dict with `id`/`name`, consumed as `channel_obj["id"]` / `channel_obj.get("name")` in Tasks 6/7. `post_message` returns `{"ts","channel"}`, consumed by `send_message`. `SlackClient` method names (`search_messages`, `conversations_replies`, `conversations_history`, `list_public_channels`, `get_permalink`, `resolve_users`, `post_message`) match their call sites in tools. Tool return shape `{"result"|"error": str}` is uniform.
