"""Агрегированная telemetry перехода на session-first transport."""

from __future__ import annotations

from collections import Counter
from threading import Lock

_LOCK = Lock()
_COUNTS: Counter[str] = Counter()
_ALLOWED = frozenset(
    {
        "server_session_bridge",
        "admin_server_session_bridge",
    }
)


def record_auth_transport(source: str) -> None:
    """Увеличить только агрегированный счётчик без identity данных."""

    if source not in _ALLOWED:
        raise ValueError("Неизвестный auth transport source")
    with _LOCK:
        _COUNTS[source] += 1


def auth_transport_snapshot() -> dict[str, int]:
    """Вернуть безопасный aggregate snapshot session bridge."""

    with _LOCK:
        return {name: int(_COUNTS.get(name, 0)) for name in _ALLOWED}


__all__ = ["auth_transport_snapshot", "record_auth_transport"]
