"""MCP tool definitions (populated in later tasks)."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .app import mcp  # noqa: F401

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
