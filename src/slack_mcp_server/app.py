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
