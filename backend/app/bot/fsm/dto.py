"""FSM DTO and constants for EFHC bot conversation state."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from app.lib.time import utcnow

StateKey = tuple[int, int]


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value else default
    except ValueError:
        return default


DEFAULT_STATE_TTL_SECONDS: int = _env_int(
    "BOT_STATE_TTL_SECONDS", 15 * 60
)
DEFAULT_GC_INTERVAL_SECONDS: int = _env_int(
    "BOT_STATE_GC_INTERVAL", 60
)
MAX_STATE_DATA_BYTES: int = _env_int(
    "BOT_STATE_DATA_LIMIT", 4096
)


def _now_ts() -> float:
    return float(utcnow().timestamp())


def _expires_ts() -> float:
    return float(utcnow().timestamp()) + DEFAULT_STATE_TTL_SECONDS


class BotStates:
    """Canonical string constants for bot FSM states."""

    IDLE = "idle"
    TASK_AWAIT_PROOF = "task.await_proof"
    TASK_AWAIT_LINK = "task.await_link"
    SHOP_AWAIT_MEMO = "shop.await_memo"
    WITHDRAW_AWAIT_AMOUNT = "withdraw.await_amount"
    ADMIN_BROADCAST_TEXT = "admin.broadcast_text"


@dataclass
class ConversationState:
    """Single JSON-safe conversation state unit."""

    state: str = BotStates.IDLE
    data: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=_now_ts)
    expires_at: float = field(default_factory=_expires_ts)

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else _now_ts()
        return now >= (self.expires_at or 0)

    def touch(self, ttl: int | None = None) -> None:
        now = _now_ts()
        self.updated_at = now
        self.expires_at = now + (ttl or DEFAULT_STATE_TTL_SECONDS)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "data": self.data,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> ConversationState:
        return ConversationState(
            state=str(d.get("state") or BotStates.IDLE),
            data=dict(d.get("data") or {}),
            updated_at=float(d.get("updated_at") or _now_ts()),
            expires_at=float(
                d.get("expires_at")
                or (_now_ts() + DEFAULT_STATE_TTL_SECONDS)
            ),
        )
