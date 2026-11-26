"""Бессрочный import-seam обслуживания задач.

Решение цикла 1728: этот модуль НЕ является отдельным maintenance engine и
НЕ имеет отношения к TON watcher. Он только реэкспортирует канонический
``tasks_autorestart.run_once`` для исторического import path.

ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ: не переносить сюда вторую реализацию, таймеры или
TON-maintenance и не удалять модуль только из-за отсутствия caller. Новый код
использует ``tasks_autorestart``; compatibility path сохраняется бессрочно.
"""

from app.scheduler.tasks_autorestart import run_once

__all__ = ["run_once"]
