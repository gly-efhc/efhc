"""Бессрочный фасад совместимости исторического имени Admin main handlers.

Совместимый фасад исторического имени: этот точный маркер оставлен намеренно,
чтобы provider-boundary guard отличал compatibility wrapper от реального handler.

Решение цикла 1728 для будущих аудитов: двойное подчёркивание в имени файла
не означает ошибку, дубль runtime-router или кандидат на автоматический cleanup.
Реальная реализация живёт в ``admin_main_handlers``; этот модуль только
реэкспортирует ТОТ ЖЕ handler/router/keyboard для старых import paths.

Новый код должен использовать ``admin_main_handlers``. Здесь нельзя создавать
новую Admin business-логику, второй router или альтернативные права доступа.
Отсутствие current callers не разрешает удалить compatibility seam без
отдельного решения пользователя и полного delete-proof.
"""

from __future__ import annotations

from app.bot.handlers.admin.admin_main_handlers import handler, router
from app.bot.keyboards import kb_admin_entry

ADMIN_HUB_LABEL = "Admin Hub"

__all__ = ["ADMIN_HUB_LABEL", "handler", "kb_admin_entry", "router"]
