"""MCP server instance — imported by both server.py and tools.py."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from mcp.server.mcpserver import MCPServer

from . import __version__


@contextlib.asynccontextmanager
async def _lifespan(app: MCPServer) -> AsyncIterator[None]:  # noqa: ARG001
    """Close the Slack HTTP client on server shutdown."""
    yield
    from .client import close_slack_client  # noqa: PLC0415

    await close_slack_client()


# MCP SDK 2.x: FastMCP was renamed MCPServer. Pass the version explicitly — 2.x
# reports an empty serverInfo.version otherwise.
mcp = MCPServer("slack-mcp", version=__version__, lifespan=_lifespan)
