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
