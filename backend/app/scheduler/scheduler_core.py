"""Бессрочный фасад старого ``scheduler_core.tick``.

Канонический runtime — ``SchedulerService.run_single_tick``. Решение цикла
1728 запрещает превращать этот compatibility entrypoint во второй scheduler
engine: он обязан оставаться тонким делегированием к тому же сервису.

ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ: даже при отсутствии прямого caller ``tick``
сохраняется ради исторических импортов. Новый код вызывает SchedulerService
напрямую; удалить фасад можно только по отдельному решению и delete-proof.
"""

from __future__ import annotations

from app.services.scheduler_service import SchedulerService


async def tick() -> None:
    """Запустить ровно один тик через канонический ``SchedulerService``."""
    await SchedulerService().run_single_tick()


__all__ = ["tick"]
