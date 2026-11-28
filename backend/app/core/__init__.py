# backend/app/core/init.py
# ======================================================================
# Назначение кода:
# Единая точка входа ядра EFHC Bot: загрузка настроек, первичная
# инициализация логирования, запуск проверок «канона» (system_locks) и
# безопасный экспорт утилит ядра во внешние модули.
#
# Канон/инварианты:
# • Источник истины: config_core.get_settings() (без локальных дублей).
# • Проверки «канона»: system_locks.* (VIP/GEN/sec, запрет P2P/обратной
#   конверсии, требование Idempotency-Key для денежных POST).
# • Денежных операций здесь нет (только конфиг/проверки/экспорты).
#
# ИИ-защита/самовосстановление:
# • boot_core() запускает стартовые проверки и возвращает сводку.
# • _run_system_locks() адаптивно ищет доступную функцию в system_locks.
# • core_health() возвращает отчёт (ok + список ошибок/варнингов).
#
# Запреты:
# • Не определяем бизнес-логики и не импортируем тяжёлые слои (CRUD).
# • Не дублируем числовые ставки/константы — используем settings.
# ======================================================================

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import system_locks, utils_core
from .config_core import get_settings
from .logging_core import get_logger

try:
    # security_core может зависеть от внешних пакетов
    # LOCK: Repo Must Be Importable — импорт ядра не должен падать при
    # отсутствии optional deps в средах тестов/анализа.
    from . import security_core  # type: ignore
except Exception:  # pragma: no cover
    security_core = None  # type: ignore

# Версия ядра (повышать при несовместимых изменениях ядра)
CORE_VERSION = "1.0.0"

logger = get_logger(__name__)

__all__ = [
    "CORE_VERSION",
    "get_settings",
    "logger",
    "boot_core",
    "core_health",
    "security_core",
    "utils_core",
]


def _run_system_locks(settings) -> dict[str, Any]:
    """Запускает стартовые проверки «канона».

    Выбирает доступную функцию из system_locks и возвращает
    диагностический словарь.
    """
    candidates = [
        "enforce_canon_or_raise",
        "validate_canon_or_raise",
        "startup_check",
        "run",
    ]
    for name in candidates:
        fn = getattr(system_locks, name, None)
        if not callable(fn):
            continue

        try:
            # Предполагается, что при нарушении бросит исключение.
            fn(settings)
            return {"ok": True, "runner": name, "error": None}
        except Exception as exc:
            logger.exception(
                "System locks failed via %s: %s",
                name,
                exc,
            )
            return {"ok": False, "runner": name, "error": repr(exc)}

    # Если ничего не нашли — не крит, но сообщим (ранние этапы сборки).
    warn = (
        "No startup system_locks runner found; "
        "checks were not executed."
    )
    logger.warning(warn)
    return {"ok": False, "runner": None, "error": warn}


def _safe_num(val: Any, kind: str) -> float | None:
    """Пытается привести значение к float для базовых sanity-checks."""
    try:
        return float(val)
    except Exception:
        logger.warning("core_health: %s is not numeric (%r)", kind, val)
        return None


def boot_core() -> dict[str, Any]:
    """Безопасная инициализация ядра.

    Загружает настройки, запускает проверки «канона», пишет лог и
    возвращает сводку.
    """
    ts = datetime.now(UTC).isoformat()
    settings = get_settings()

    logger.info(
        "EFHC Core boot: version=%s env=%s schema=%s",
        CORE_VERSION,
        getattr(settings, "ENVIRONMENT", "unknown"),
        getattr(settings, "DB_SCHEMA_CORE", "efhc_core"),
    )

    health = core_health()
    locks = _run_system_locks(settings)

    if not health.get("ok"):
        logger.warning("Core health warnings: %s", health.get("errors"))

    if not locks.get("ok"):
        # Не «роняем» процесс — отдаём сводку. Админка увидит ошибку.
        logger.error(
            "System locks did not pass: %s",
            locks.get("error"),
        )

    return {
        "timestamp_utc": ts,
        "core_version": CORE_VERSION,
        "health": health,
        "locks": locks,
    }


def core_health() -> dict[str, Any]:
    """Быстрые sanity-checks по ключевым настройкам.

    Возвращает отчёт для логов/админки и не падает исключениями.
    """
    settings = get_settings()
    errors: list[str] = []

    base = getattr(settings, "GEN_PER_SEC_BASE_KWH", None)
    vip = getattr(settings, "GEN_PER_SEC_VIP_KWH", None)
    schema = getattr(settings, "DB_SCHEMA_CORE", None)
    tick = getattr(settings, "SCHEDULER_TICK_SECONDS", None)

    base_num = _safe_num(base, "GEN_PER_SEC_BASE_KWH")
    vip_num = _safe_num(vip, "GEN_PER_SEC_VIP_KWH")
    tick_num = _safe_num(tick, "SCHEDULER_TICK_SECONDS")

    if base_num is None or base_num <= 0:
        errors.append("GEN_PER_SEC_BASE_KWH must be positive numeric.")
    if vip_num is None or vip_num <= 0:
        errors.append("GEN_PER_SEC_VIP_KWH must be positive numeric.")
    if not schema:
        errors.append("DB_SCHEMA_CORE must be set.")
    if tick_num is None or tick_num <= 0:
        errors.append(
            "SCHEDULER_TICK_SECONDS must be positive numeric."
        )

    snapshot = {
        # ВНИМАНИЕ: не выводим чувствительные данные (ключи/пароли/URL).
        "PROJECT_NAME": getattr(settings, "PROJECT_NAME", None),
        "ENVIRONMENT": getattr(settings, "ENVIRONMENT", None),
        "DB_SCHEMA_CORE": schema,
        "GEN_PER_SEC_BASE_KWH": base,
        "GEN_PER_SEC_VIP_KWH": vip,
        "SCHEDULER_TICK_SECONDS": tick,
        "STRICT_IDEMPOTENCY": getattr(
            settings,
            "STRICT_IDEMPOTENCY",
            None,
        ),
        "FORBID_NEGATIVE_BANK_BALANCE": getattr(
            settings,
            "FORBID_NEGATIVE_BANK_BALANCE",
            None,
        ),
    }

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "snapshot": snapshot,
    }


# ======================================================================
# Пояснения:
# • Этот __init__ экспортирует get_settings и предоставляет
#   boot_core() / core_health() для старта и диагностики.
# • boot_core() следует вызывать в main.py и/или entry-point
#   планировщика.
# • При изменении API system_locks адаптер _run_system_locks() остаётся
#   безопасной точкой интеграции.
# ======================================================================
