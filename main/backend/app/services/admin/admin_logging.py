# backend/app/services/admin/admin_logging.py
# =====================================================================
# EFHC Bot — Аудит действий администраторов (admin_action_log)
#
# Канон:
# - Таблица: efhc_admin.admin_action_log (ORM: AdminActionLog)
# - Любые админ-действия логируются.
# - Логирование best-effort: не ломает основную операцию.
# =====================================================================

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
S = get_settings()

SCHEMA_ADMIN: str = canon_schema(
    getattr(S, "DB_SCHEMA_ADMIN", "efhc_admin") or "efhc_admin",
)


class AdminLog(BaseModel):
    id: int = Field(...)
    actor_global_id: str | None = None
    admin_id: int | None = None
    action: str = Field(..., min_length=1, max_length=64)
    target_type: str | None = None
    target_id: str | None = None
    created_at: str = Field(...)
    details_json: Any | None = None
    ip: str | None = None
    user_agent: str | None = None


class Pagination(BaseModel):
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)
    sort_desc: bool = Field(True)


class AdminLogger:
    """Сервис логирования действий администраторов."""

    @staticmethod
    def _build_details_json(
        *,
        details: str | None,
        before: Any | None,
        after: Any | None,
        meta: dict[str, Any] | None,
        error: str | None,
        admin_id_raw: int | None = None,
        actor_global_id: int | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {}
        if details is not None:
            payload["details"] = details
        if before is not None:
            payload["before"] = before
        if after is not None:
            payload["after"] = after
        if meta:
            payload["meta"] = meta
        if error is not None:
            payload["error"] = error
        if admin_id_raw is not None:
            payload["admin_id_raw"] = admin_id_raw
        if actor_global_id is not None:
            payload["actor_global_id"] = actor_global_id
        if not payload:
            return None
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    async def write(
        db: AsyncSession,
        *,
        actor_global_id: int | None,
        action: str,
        admin_id: int | None = None,
        entity: str,
        entity_id: int | None = None,
        details: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        before: Any | None = None,
        after: Any | None = None,
        meta: dict[str, Any] | None = None,
        error: str | None = None,
        required: bool = False,
    ) -> None:
        """Записать действие админа в ``admin_action_log``.

        По умолчанию сохраняется историческое best-effort поведение. Для
        финансовых/обязательных W A операций ``required=True`` превращает
        невозможность записи audit в исключение, чтобы вызывающий сервис мог
        откатить ту же DB transaction вместе с бизнес-изменением.
        """
        try:
            action_s = (action or "").strip()[:64]
            target_type_s = (entity or "").strip()[:64] or None
            if entity_id is None:
                target_id_s = None
            else:
                target_id_s = str(int(entity_id))[:128]

            details_s = None if details is None else str(details)[:4000]
            ip_s = None if ip is None else str(ip)[:64]
            ua_s = None if user_agent is None else str(user_agent)[:512]

            if not action_s:
                if required:
                    raise ValueError("Admin audit action обязателен")
                logger.warning("AdminLogger.write: empty action")
                return

            details_json_val = AdminLogger._build_details_json(
                details=details_s,
                before=before,
                after=after,
                meta=meta,
                error=error,
                actor_global_id=actor_global_id,
            )

            sql = text(
                "\n".join(
                    [
                        (
                            "INSERT INTO "
                            + SCHEMA_ADMIN
                            + ".admin_action_log"
                        ),
                        "(admin_id, actor_global_id, action,",
                        " target_type, target_id, details_json, ip,",
                        " user_agent)",
                        "VALUES (:admin_id, :actor_global_id, :action,",
                        " :target_type, :target_id,",
                        " CAST(:details_json AS jsonb),",
                        " :ip,",
                        " :user_agent)",
                    ]
                )
            )

            params = {
                "admin_id": None if admin_id is None else int(admin_id),
                "actor_global_id": (
                    None
                    if actor_global_id is None
                    else int(actor_global_id)
                ),
                "action": action_s,
                "target_type": target_type_s,
                "target_id": target_id_s,
                "details_json": details_json_val,
                "ip": ip_s,
                "user_agent": ua_s,
            }

            try:
                async with db.begin_nested():
                    await db.execute(sql, params)
                return
            except Exception as e:
                logger.warning(
                    "AdminLogger.write: insert failed"
                    " (admin_id=%s): %s",
                    admin_id,
                    e,
                )

            details_json_val2 = AdminLogger._build_details_json(
                details=details_s,
                before=before,
                after=after,
                meta=meta,
                error=error,
                actor_global_id=actor_global_id,
                admin_id_raw=None
                if admin_id is None
                else int(admin_id),
            )
            params2 = dict(params)
            params2["admin_id"] = None
            params2["details_json"] = details_json_val2
            try:
                async with db.begin_nested():
                    await db.execute(sql, params2)
                return
            except Exception as e:
                logger.warning(
                    "AdminLogger.write: fallback insert failed"
                    " (admin_id=%s): %s",
                    admin_id,
                    e,
                )
                if required:
                    raise RuntimeError(
                        "Обязательный Admin audit не записан"
                    ) from e

        except Exception as e:
            logger.error("AdminLogger.write: failed: %s", e)
            if required:
                raise

    @staticmethod
    async def list_logs(
        db: AsyncSession,
        *,
        limit: int = 50,
        offset: int = 0,
        sort_desc: bool = True,
        actor_global_id: int | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        entity: str | None = None,
    ) -> list[AdminLog]:
        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500
        if offset < 0:
            offset = 0

        where: list[str] = ["1=1"]
        params: dict[str, Any] = {
            "limit": int(limit),
            "offset": int(offset),
        }

        if actor_global_id is not None:
            where.append("actor_global_id = :gid")
            params["gid"] = int(actor_global_id)

        if admin_id is not None:
            where.append("admin_id = :aid")
            params["aid"] = int(admin_id)

        if action:
            where.append("action = :act")
            params["act"] = str(action).strip()[:64]

        if entity:
            where.append("target_type = :tt")
            params["tt"] = str(entity).strip()[:64]

        order = "DESC" if sort_desc else "ASC"

        sql = text(
            "\n".join(
                [
                    "SELECT id, actor_global_id, admin_id, action,",
                    " target_type,",
                    " target_id, details_json, ip, user_agent,",
                    " created_at",
                    "FROM " + SCHEMA_ADMIN + ".admin_action_log",
                    f"WHERE {' AND '.join(where)}",
                    f"ORDER BY id {order}",
                    "LIMIT :limit OFFSET :offset",
                ]
            )
        )

        r: Result = await db.execute(sql, params)
        rows = r.fetchall()

        out: list[AdminLog] = []
        for row in rows:
            with suppress(Exception):
                ts = getattr(row, "created_at", None)
                iso = getattr(ts, "isoformat", None)
                ts_out = iso() if callable(iso) else str(ts)

                det = getattr(row, "details_json", None)
                out.append(
                    AdminLog(
                        id=int(row.id),
                        actor_global_id=(
                            f"{int(row.actor_global_id):010d}"
                            if row.actor_global_id is not None
                            else None
                        ),
                        admin_id=None
                        if row.admin_id is None
                        else int(row.admin_id),
                        action=str(row.action),
                        target_type=getattr(row, "target_type", None),
                        target_id=getattr(row, "target_id", None),
                        created_at=ts_out,
                        details_json=det,
                        ip=getattr(row, "ip", None),
                        user_agent=getattr(row, "user_agent", None),
                    )
                )

        return out

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        pg: Pagination,
        actor_global_id: int | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        entity: str | None = None,
    ) -> list[AdminLog]:
        return await AdminLogger.list_logs(
            db,
            limit=int(pg.limit),
            offset=int(pg.offset),
            sort_desc=bool(pg.sort_desc),
            actor_global_id=actor_global_id,
            admin_id=admin_id,
            action=action,
            entity=entity,
        )


__all__ = ["AdminLog", "Pagination", "AdminLogger"]
