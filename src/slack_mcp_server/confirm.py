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
