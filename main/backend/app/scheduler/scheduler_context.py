"""Бессрочный compatibility-контекст старого API планировщика.

Решение цикла 1728: действующий ``SchedulerService`` не использует
``TickContext`` как свой канонический runtime context. Класс сохраняется только
как import/type seam для исторических потребителей. Новый scheduler-код не
должен строить архитектуру вокруг него и не должен трактовать его наличие как
обязательный внутренний контекст SchedulerService.

ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ: «не используется текущим SchedulerService» —
это причина оставить тип тонким, но НЕ причина удалить его автоматически.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TickContext:
    """Исторический контекст времени одного тика; compatibility-only."""

    started_at: datetime


__all__ = ["TickContext"]
