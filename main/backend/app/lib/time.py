# backend/app/lib/time.py

"""SSOT времени приложения EFHC.

Business/runtime код, которому важно именно прошедшее игровое время, должен
использовать tz-aware UTC через :func:`utcnow`.

ApplicationClock привязывает UTC-эпоху процесса к ``time.monotonic_ns()``.
Поэтому ручной/NTP скачок системных wall-clock часов во время жизни процесса
не добавляет и не отнимает генерацию, lifetime панели или scheduler interval.
После штатного рестарта новая эпоха снова берётся из UTC ОС.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta


class ApplicationClock:
    """Монотонный UTC clock процесса для elapsed-time business logic."""

    def __init__(self) -> None:
        self._anchor_utc = datetime.now(UTC)
        self._anchor_monotonic_ns = time.monotonic_ns()
        self._lock = threading.Lock()
        self._last_utc = self._anchor_utc

    def now_utc(self) -> datetime:
        """Вернуть UTC, растущий только вместе с monotonic clock процесса."""

        elapsed_ns = max(0, time.monotonic_ns() - self._anchor_monotonic_ns)
        candidate = self._anchor_utc + timedelta(microseconds=elapsed_ns // 1_000)
        with self._lock:
            if candidate < self._last_utc:
                return self._last_utc
            self._last_utc = candidate
            return candidate


_APPLICATION_CLOCK = ApplicationClock()


def utcnow() -> datetime:
    """Вернуть tz-aware UTC ApplicationClock."""

    return _APPLICATION_CLOCK.now_utc()
