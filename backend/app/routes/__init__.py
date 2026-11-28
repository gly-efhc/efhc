# backend/app/routes/__init__.py
# =====================================================================
# Назначение кода:
# Единая точка подключения HTTP-роутов EFHC Bot. Этот модуль агрегирует
# подмодули роутов и предоставляет:
# • общий APIRouter (api_router), в который включены найденные роуты;
# • функцию register(app, prefix="") для удобного подключения в FastAPI;
# • диагностику подключённых/пропущенных модулей для наблюдаемости.
#
# Канон/инварианты:
# • Этот модуль НЕ выполняет бизнес-логику и НЕ трогает деньги — только
# проводка
# маршрутов. Денежные правила (Idempotency-Key, банк и др.) реализуются
# в самих роут-модулях и сервисах.
# • Мягкая деградация: отсутствие части модулей не должно
# «ронять» процесс (полезно при поэтапном деплое/миграциях).
# • Никаких суточных расчётов/констант здесь нет и быть не должно.
#
# ИИ-защита/самовосстановление:
# • Мягкие импорты: каждый модуль подключается через try/except.
#   При неудаче пишем предупреждение в лог и продолжаем.
# • Диагностика: список присоединённых/пропущенных роутов,
# доступны функции list_registered_routes() и list_missing_routes().
# • Избегаем побочных эффектов при импорте: только сборка маршрутов.
#
# Запреты:
# • Нет SQL и вызовов сервисов — только import и include_router.
# • Нет динамического изменения префиксов: модуль задаёт свой prefix.
#   Примеры: "/user", "/panels", "/admin".
# =====================================================================

from __future__ import annotations

from importlib import import_module

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from fastapi import APIRouter, FastAPI

logger = get_logger(__name__)

# --------------------------------------------------------------------
# Перечень ожидаемых модулей роутов (по канонической схеме)
# Порядок важен для читабельности / предсказуемости логов.
# Каждый модуль должен экспортировать переменную `router: APIRouter`.
# --------------------------------------------------------------------
ROUTERS_EXPECTED: tuple[str, ...] = (
    # публичные разделы
    "user_routes",
    "me_routes",
    "profile_history_routes",
    "panels_routes",
    "exchange_routes",
    "ranks_routes",
    "referrals_routes",
    "shop_routes",
    "hub_routes",
    "shopfront_routes",
    "deposit_routes",
    "payment_intents_routes",
    "auth_session_routes",
    "profile_avatar_routes",
    "auth_telegram_routes",
    "auth_ton_routes",
    "wallets_routes",
    "skins_routes",
    "withdraw_routes",
    "tasks_routes",
    "ads_routes",
    "nft_routes",
    "sync_routes",
    # системные (health/cron/webhook)
    "system_routes",
    # админские разделы
    "admin_routes",
    "admin_users_routes",
    "admin_panels_routes",
    "admin_logs_routes",
    "admin_observability_routes",
    "admin_reports_routes",
    "admin_bonus_routes",
    "admin_withdrawals_routes",
    "admin_shop_routes",
    "admin_hub_routes",
    "admin_sale_packages_routes",
    "admin_ads_routes",
    "admin_referral_routes",
    "admin_tasks_routes",
    "admin_templates_routes",
)

# --------------------------------------------------------------------
# Глобальный агрегатор маршрутов. В main.py обычно делают:
# from app.routes import register
# app = FastAPI(...)
# register(app, prefix="")  # финальный /api добавляет app
# --------------------------------------------------------------------
api_router = APIRouter()

# Внутренняя телеметрия: что подключили/что нет.
_ATTACHED: list[str] = []
_MISSING: list[str] = []
_IMPORT_ERRORS: dict[str, str] = {}

REQUIRED_PRODUCTION_ROUTES = frozenset(ROUTERS_EXPECTED)
OPTIONAL_PRODUCTION_ROUTES: frozenset[str] = frozenset()


def _try_include(module_basename: str) -> None:
    """Импортировать модуль и включить его router в api_router."""
    fqmn = f"app.routes.{module_basename}"
    try:
        mod = import_module(fqmn)
    except Exception as e:
        logger.warning(
            "routes: пропущен модуль %s (импорт не удался): %s",
            fqmn,
            e,
        )
        _MISSING.append(module_basename)
        _IMPORT_ERRORS[module_basename] = str(e)
        return

    router = getattr(mod, "router", None)
    if not isinstance(router, APIRouter):
        logger.warning(
            "routes: пропущен модуль %s (нет router: APIRouter)",
            fqmn,
        )
        _MISSING.append(module_basename)
        _IMPORT_ERRORS[module_basename] = "router is not APIRouter"
        return

    try:
        api_router.include_router(router)
        _ATTACHED.append(module_basename)
        logger.info("routes: подключён модуль %s", fqmn)
    except Exception as e:
        logger.error(
            "routes: ошибка include_router для %s: %s",
            fqmn,
            e,
        )
        _MISSING.append(module_basename)
        _IMPORT_ERRORS[module_basename] = str(e)


# При импорте модуля собираем доступные роуты (мягко).
for _name in ROUTERS_EXPECTED:
    _try_include(_name)


# --------------------------------------------------------------------
# Публичные утилиты
# --------------------------------------------------------------------


def register(app: FastAPI, prefix: str = "") -> None:
    """
    Регистрирует агрегированный роутер в приложении FastAPI.

    Args:
        app:   экземпляр FastAPI.
        prefix: базовый префикс для маршрутов (обычно "" или "/api").
    """
    settings = get_settings()
    if settings.env_normalized in {"prod", "stage"}:
        missing = sorted(
            REQUIRED_PRODUCTION_ROUTES.intersection(_MISSING)
        )
        if missing:
            details = "; ".join(
                f"{name}: {_IMPORT_ERRORS.get(name, 'unknown')}"
                for name in missing
            )
            raise RuntimeError(
                "Mandatory production routes failed to load: "
                + details
            )
    app.include_router(api_router, prefix=prefix)
    attached = ",".join(_ATTACHED) if _ATTACHED else "-"
    missing_label = ",".join(_MISSING) if _MISSING else "-"
    logger.info(
        "routes: зарегистрирован агрегатор (prefix=%r).",
        prefix,
    )
    logger.info("routes: подключено: %s", attached)
    logger.info("routes: пропущено: %s", missing_label)


def list_registered_routes() -> list[str]:
    """Список модулей роутов, которые подключены."""
    return list(_ATTACHED)


def list_missing_routes() -> list[str]:
    """Список модулей роутов, которые не удалось подключить."""
    return list(_MISSING)


__all__ = [
    "api_router",
    "register",
    "list_registered_routes",
    "list_missing_routes",
    "ROUTERS_EXPECTED",
    "REQUIRED_PRODUCTION_ROUTES",
    "OPTIONAL_PRODUCTION_ROUTES",
]
