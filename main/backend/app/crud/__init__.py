# backend/app/crud/init.py
# =====================================================================
# Назначение кода:
# Централизованный пакет CRUD-слоя (доступ к данным без бизнес-логики).
# Агрегирует модули, формирует реестр, даёт самодиагностику наличия
# ключевых
# символов для сервисов/роутов.
#
# Канон/инварианты (важно):
# • Здесь НЕТ денежных операций и пересчёта балансов — только факты БД.
# Все деньги идут через services/transactions_service.py.
# • Пагинация реализуется курсорами (id ASC), без OFFSET.
# • Идемпотентность: уникальные индексы + read-through в сервисах.
#
# ИИ-защита/самовосстановление:
# • «Мягкий» импорт: отсутствие CRUD-модуля не валит весь пакет.
# • CRUD_REGISTRY содержит только успешно загруженные модули;
# health_check() отчётно показывает недостающие файлы/символы.
#
# Запреты:
# • Не добавлять бизнес-функции/шорткаты для денежных операций.
# • Не дублировать константы/утилиты — они живут в core/config_core.py и
# deps.py.
# =====================================================================

from __future__ import annotations

import importlib

# --------------------------------------------------------------------
# «Мягкий» импорт CRUD-модулей
# --------------------------------------------------------------------


def _try_import(local_module: str) -> object | None:
    """
    Пытается загрузить .<local_module> относительно текущего пакета.
    Возвращает модуль или None (если файла нет/ошибка импорта).
    Никаких исключений наружу — пакет не падает.
    """
    try:
        return importlib.import_module(
            f".{local_module}",
            package=__name__,
        )
    except Exception:
        return None


# Карта логических имён → физические файлы
_MODULES_MAP: dict[str, str] = {
    "user": "user_crud",
    "transactions": "transactions_crud",
    "panels": "panels_crud",
    "referrals": "referrals_crud",
    "tasks": "tasks_crud",
    "shop": "shop_crud",  # может отсутствовать на ранних этапах
    "orders": "order_crud",  # единое имя для order_crud.py
}

# Загружаем модули «мягко» и складываем в globals() с короткими алиасами
_LOADED: dict[str, object | None] = {}
for alias, modname in _MODULES_MAP.items():
    module = _try_import(modname)
    _LOADED[alias] = module
    # чтобы работать как раньше: from app.crud import user, ...
    globals()[alias] = module

# --------------------------------------------------------------------
# Реестр доступных модулей (только успешно загруженные)
# --------------------------------------------------------------------
CRUD_REGISTRY: dict[str, object] = {
    k: v for k, v in _LOADED.items() if v is not None
}

# Формируем __all__: алиасы модулей + утилиты пакета
__all__ = list(CRUD_REGISTRY.keys()) + ["CRUD_REGISTRY", "health_check"]

# --------------------------------------------------------------------
# Самопроверка наличия ключевых символов
# --------------------------------------------------------------------


def health_check() -> list[tuple[str, bool, list[str]]]:
    """
    Назначение: вернуть список проверок
    (module_name, ok, missing_symbols)
    без исключений. Используется при старте сервиса/в админ-панели.

    Мы проверяем наличие «ядровых» символов, которые сервисы ожидают.
    Отсутствие файла -> (ok=False, ["module_not_loaded"]).
    Отсутствие конкретных функций -> (ok=False, ["foo", "bar"]).
    """
    checks: list[tuple[str, bool, list[str]]] = []

    # Presence-only registry. It does not prove that a symbol is wired
    # into a production call path. Runtime tests provide that proof.
    # Historically, activate_referral existed here while duplicate
    # inline SQL remained the real implementation.
    SYMBOLS_PRESENT: dict[str, list[str]] = {
        # user_crud.py
        "user": [
            "get_user_by_telegram_subject",
            "list_users_cursor",
        ],
        # transactions_crud.py
        "transactions": [
            "insert_transfer_log_readthrough",
            "upsert_ton_inbox_readthrough",
        ],
        # panels_crud.py
        "panels": [
            "create_panel",
            "lock_active_panels_for_energy",
            "accrue_generated_kwh",
        ],
        # order_crud.py
        "orders": [
            "create_order_pending_payment",
            "mark_paid_by_external",
            "set_status_guarded",
        ],
        # referrals_crud.py / tasks_crud.py / shop
        # требования могут эволюционировать
        "referrals": [
            "activate_referral",
            "list_active_refs_cursor",
            "list_inactive_refs_cursor",
            "count_total_and_active",
        ],
        "tasks": [],
        "shop": [],
    }

    for alias in _MODULES_MAP:
        module_obj = _LOADED.get(alias)
        required_symbols = SYMBOLS_PRESENT.get(alias, [])
        if module_obj is None:
            checks.append((alias, False, ["module_not_loaded"]))
            continue
        missing = [
            name
            for name in required_symbols
            if not hasattr(module_obj, name)
        ]
        checks.append((alias, len(missing) == 0, missing))

    return checks


# =====================================================================
# Пояснения (для разработчиков/ревью):
# • Мы сохранили прежние короткие алиасы (user, panels, ...),
#   но сделали импорт
# «мягким»:
# отсутствующий файл CRUD теперь не роняет весь пакет crud.
# • CRUD_REGISTRY содержит только то, что реально загружено — удобно для
# диагностики и UI.
# • health_check() — мягкая проверка для админки/логов: видно, какого
# файла/символа нет.
# • Денежные операции запрещены на CRUD-уровне — только операции БД.
# =====================================================================
