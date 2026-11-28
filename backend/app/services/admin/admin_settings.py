# backend/app/services/admin/admin_settings.py
# ======================================================================
# EFHC Bot — Системные настройки админ-панели (K/V-хранилище)
# ----------------------------------------------------------------------
# Назначение:
# - Централизованное управление параметрами из админки.
# - Изменения валидируются и пишутся в БД.
# - Все значения хранятся в {SCHEMA_ADMIN}.system_settings (key/value).
# - Любое изменение логируется через AdminLogger (SET_SETTING).
# ----------------------------------------------------------------------

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import (
    format_decimal_str,
    quantize_decimal,
)
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from .admin_logging import AdminLogger

logger = get_logger(__name__)
S = get_settings()

SCHEMA_ADMIN: str = canon_schema(
    getattr(S, "DB_SCHEMA_ADMIN", "efhc_admin") or "efhc_admin",
)


# ======================================================================
# DTO
# ======================================================================


class SystemSetting(BaseModel):
    """Одна настройка (key/value) + updated_at (ISO8601 UTC)."""

    key: str
    value: str
    updated_at: str | None = None


# ======================================================================
# Белый список ключей
# ======================================================================


ALLOWED_SETTINGS: dict[str, str] = {
    "GEN_PER_SEC_BASE_KWH": (
        "Скорость генерации kWh/сек для обычных пользователей"
    ),
    "GEN_PER_SEC_VIP_KWH": "Скорость генерации kWh/сек для VIP",
}

_DECIMAL_KEYS: set[str] = {
    "GEN_PER_SEC_BASE_KWH",
    "GEN_PER_SEC_VIP_KWH",
}

_INT_KEYS: set[str] = set()


# ======================================================================
# Вспомогательная валидация
# ======================================================================


def _normalize_key(key: str) -> str:
    """Нормализует ключ (upper) и проверяет, что он разрешён."""

    k = str(key or "").strip().upper()
    if k not in ALLOWED_SETTINGS:
        raise ValueError("Недопустимый ключ настройки")
    return k


def _normalize_value(key: str, value: Any) -> str:
    """Нормализует и валидирует значение в зависимости от ключа."""

    key_upper = _normalize_key(key)
    raw = str(value)

    if key_upper in _DECIMAL_KEYS:
        try:
            q = quantize_decimal(raw, 8, "DOWN")
        except Exception as e:
            raise ValueError(
                f"Значение для {key_upper} должно быть числом"
            ) from e

        if q <= 0:
            raise ValueError(
                f"Значение для {key_upper} должно быть положительным"
            )
        return str(format_decimal_str(q, 8))

    if key_upper in _INT_KEYS:
        try:
            ivalue = int(raw)
        except Exception as e:
            raise ValueError(
                f"Значение для {key_upper} должно быть целым числом"
            ) from e
        if ivalue <= 0:
            raise ValueError(
                f"Значение для {key_upper} должно быть положительным"
            )
        return str(ivalue)

    return raw


# ======================================================================
# Сервис
# ======================================================================


class SettingsService:
    """Сервис системных настроек (get/mget + set/mset)."""

    @staticmethod
    async def get(
        db: AsyncSession,
        key: str,
    ) -> SystemSetting | None:
        norm_key = _normalize_key(key)
        sql = text(
            "\n".join(
                [
                    "SELECT key, value, updated_at",
                    "FROM " + SCHEMA_ADMIN + ".system_settings",
                    "WHERE key = :k",
                    "LIMIT 1",
                ]
            )
        )
        r: Result = await db.execute(sql, {"k": norm_key})
        row = r.fetchone()
        if not row:
            return None

        upd = getattr(row, "updated_at", None)
        updated_at: str | None
        if upd is None:
            updated_at = None
        elif hasattr(upd, "isoformat"):
            updated_at = upd.isoformat()
        else:
            updated_at = str(upd)

        return SystemSetting(
            key=str(row.key),
            value=str(row.value),
            updated_at=updated_at,
        )

    @staticmethod
    async def mget(
        db: AsyncSession,
        keys: Sequence[str],
    ) -> list[SystemSetting]:
        if not keys:
            return []

        norm_keys: list[str] = []
        for k in keys:
            try:
                norm_keys.append(_normalize_key(k))
            except ValueError:
                logger.warning(
                    "SettingsService.mget: игнорируем"
                    " неизвестный ключ %r",
                    k,
                )

        if not norm_keys:
            return []

        sql = text(
            "\n".join(
                [
                    "SELECT key, value, updated_at",
                    "FROM " + SCHEMA_ADMIN + ".system_settings",
                    "WHERE key = ANY(:keys)",
                    "ORDER BY key ASC",
                ]
            )
        )
        r: Result = await db.execute(sql, {"keys": list(norm_keys)})
        rows = r.fetchall()

        out: list[SystemSetting] = []
        for row in rows:
            try:
                upd = getattr(row, "updated_at", None)
                if upd is None:
                    updated_at = None
                elif hasattr(upd, "isoformat"):
                    updated_at = upd.isoformat()
                else:
                    updated_at = str(upd)

                out.append(
                    SystemSetting(
                        key=str(row.key),
                        value=str(row.value),
                        updated_at=updated_at,
                    )
                )
            except Exception as e:
                logger.warning(
                    "SettingsService.mget: пропущена битая строка: %s",
                    e,
                )
        return out

    @staticmethod
    async def set(
        db: AsyncSession,
        key: str,
        value: Any,
        actor_global_id: int | None = None,
        admin_id: int | None = None,
    ) -> SystemSetting:
        norm_key = _normalize_key(key)
        norm_val = _normalize_value(norm_key, value)

        sql = text(
            "\n".join(
                [
                    "INSERT INTO " + SCHEMA_ADMIN + ".system_settings",
                    "(key, value, updated_at)",
                    "VALUES (:k, :v, NOW() AT TIME ZONE 'UTC')",
                    "ON CONFLICT (key) DO UPDATE",
                    "SET value = EXCLUDED.value,",
                    "updated_at = EXCLUDED.updated_at",
                    "RETURNING key, value, updated_at",
                ]
            )
        )
        r: Result = await db.execute(
            sql, {"k": norm_key, "v": norm_val}
        )
        row = r.fetchone()
        if not row:
            raise RuntimeError("Не удалось сохранить настройку")

        upd = getattr(row, "updated_at", None)
        iso = getattr(upd, "isoformat", None)
        updated_at = iso() if callable(iso) else None

        if admin_id is not None:
            await AdminLogger.write(
                db=db,
                actor_global_id=actor_global_id,
                admin_id=admin_id,
                action="SET_SETTING",
                entity="system_settings",
                entity_id=None,
                details=f"{norm_key}={norm_val}",
            )

        return SystemSetting(
            key=str(row.key),
            value=str(row.value),
            updated_at=updated_at,
        )

    @staticmethod
    async def mset(
        db: AsyncSession,
        items: dict[str, Any],
        actor_global_id: int | None = None,
        admin_id: int | None = None,
    ) -> list[SystemSetting]:
        out: list[SystemSetting] = []
        last_error: Exception | None = None
        for k, v in items.items():
            try:
                out.append(
                    await SettingsService.set(
                        db=db,
                        key=k,
                        value=v,
                        actor_global_id=actor_global_id,
                        admin_id=admin_id,
                    )
                )
            except Exception as e:
                last_error = e

        if last_error is not None:
            raise last_error
        return out
