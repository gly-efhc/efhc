"""Бессрочный фасад исторических импортов базы данных EFHC.

Каноническая реализация находится в ``app.core.database_core``.

Решение цикла 1728 для будущих аудитов:
- этот модуль намеренно НЕ создаёт второй engine или session factory;
- ``get_engine`` и ``get_session_factory`` должны оставаться точными
  реэкспортами канонической реализации;
- отсутствие текущего caller не является доказательством, что import path
  можно удалить: он сохранён как постоянный compatibility contract;
- новый код должен импортировать канонический модуль напрямую, но cleanup
  не имеет права удалять этот фасад без отдельного решения пользователя и
  полного delete-proof.
"""

from __future__ import annotations

from app.core.database_core import get_engine, get_session_factory

__all__ = ["get_engine", "get_session_factory"]
