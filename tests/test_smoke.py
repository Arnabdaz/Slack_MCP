"""Smoke test: the package imports and exposes a configured FastMCP instance."""

from __future__ import annotations


def test_mcp_instance_name() -> None:
    from slack_mcp_server.app import mcp

    assert mcp.name == "slack-mcp"


def test_main_is_callable() -> None:
    from slack_mcp_server import main

    assert callable(main)
