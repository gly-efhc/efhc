"""Ограниченный server-side export журналов Admin Банка и Панелей."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal

from app.core.database_core import db_session
from app.core.utils_core import format_decimal_str
from app.deps import d8
from app.models.panels_models import Panel
from app.models.transactions_models import EfhcTransferLog
from sqlalchemy import desc, select

AdminLogExportScope = Literal["bank", "panels"]
ADMIN_LOG_EXPORT_BATCH_SIZE = 500
ADMIN_LOG_EXPORT_ALLOWED_ROWS = frozenset({100, 1_000, 100_000, 1_000_000})

BANK_EXPORT_HEADERS = [
    "id",
    "created_at",
    "global_id",
    "system_entity",
    "direction",
    "balance_type",
    "amount_efhc",
    "reason",
    "idempotency_key",
]
PANEL_EXPORT_HEADERS = [
    "id",
    "public_id",
    "global_id",
    "is_active",
    "created_at",
    "activated_at",
    "expires_at",
    "archived_at",
    "generated_kwh",
    "base_gen_per_sec",
    "protectively_voided",
    "dead_state",
]


def export_headers(scope: AdminLogExportScope) -> list[str]:
    """Вернуть канонический порядок колонок выбранного экспорта."""
    return (
        BANK_EXPORT_HEADERS
        if scope == "bank"
        else PANEL_EXPORT_HEADERS
    )


def _iso(value: object) -> str:
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


async def _bank_batch(before_id: int | None, *, batch_limit: int) -> list[list[str]]:
    async with db_session() as db:
        stmt = (
            select(
                EfhcTransferLog.id,
                EfhcTransferLog.created_at,
                EfhcTransferLog.global_id,
                EfhcTransferLog.system_entity,
                EfhcTransferLog.direction,
                EfhcTransferLog.balance_type,
                EfhcTransferLog.amount,
                EfhcTransferLog.reason,
                EfhcTransferLog.idempotency_key,
            )
            .where(EfhcTransferLog.system_entity == "BANK_EFHC")
            .order_by(desc(EfhcTransferLog.id))
            .limit(int(batch_limit))
        )
        if before_id is not None:
            stmt = stmt.where(EfhcTransferLog.id < before_id)
        rows = (await db.execute(stmt)).all()
    return [
        [
            str(int(row.id)),
            _iso(row.created_at),
            (
                f"{int(row.global_id):010d}"
                if row.global_id is not None
                else ""
            ),
            str(row.system_entity or ""),
            str(row.direction or ""),
            str(row.balance_type or ""),
            format_decimal_str(d8(row.amount or 0)),
            str(row.reason or ""),
            str(row.idempotency_key or ""),
        ]
        for row in rows
    ]


async def _panels_batch(before_id: int | None, *, batch_limit: int) -> list[list[str]]:
    async with db_session() as db:
        stmt = (
            select(
                Panel.id,
                Panel.public_id,
                Panel.global_id,
                Panel.is_active,
                Panel.created_at,
                Panel.activated_at,
                Panel.expires_at,
                Panel.archived_at,
                Panel.generated_kwh,
                Panel.base_gen_per_sec,
                Panel.meta,
            )
            .order_by(desc(Panel.id))
            .limit(int(batch_limit))
        )
        if before_id is not None:
            stmt = stmt.where(Panel.id < before_id)
        rows = (await db.execute(stmt)).all()
    return [
        [
            str(int(row.id)),
            str(row.public_id or ""),
            f"{int(row.global_id):010d}",
            "1" if bool(row.is_active) else "0",
            _iso(row.created_at),
            _iso(row.activated_at),
            _iso(row.expires_at),
            _iso(row.archived_at),
            format_decimal_str(d8(row.generated_kwh or 0)),
            format_decimal_str(d8(row.base_gen_per_sec or 0)),
            "1" if isinstance(row.meta, dict) and row.meta.get("protectively_voided") is True else "0",
            str(row.meta.get("dead_state") or "") if isinstance(row.meta, dict) else "",
        ]
        for row in rows
    ]


async def iter_admin_log_export(
    scope: AdminLogExportScope,
    *,
    row_limit: int | None = 100_000,
) -> AsyncIterator[list[list[str]]]:
    """Читать Admin export keyset-порциями до выбранного owner-limit."""
    if row_limit is not None and int(row_limit) not in ADMIN_LOG_EXPORT_ALLOWED_ROWS:
        raise ValueError("ADMIN_LOG_EXPORT_ROWS_INVALID")

    before_id: int | None = None
    exported = 0
    while True:
        remaining = None if row_limit is None else int(row_limit) - exported
        if remaining is not None and remaining <= 0:
            break
        batch_limit = (
            ADMIN_LOG_EXPORT_BATCH_SIZE
            if remaining is None
            else min(ADMIN_LOG_EXPORT_BATCH_SIZE, remaining)
        )
        batch = (
            await _bank_batch(before_id, batch_limit=batch_limit)
            if scope == "bank"
            else await _panels_batch(before_id, batch_limit=batch_limit)
        )
        if not batch:
            break
        yield batch
        exported += len(batch)
        before_id = int(batch[-1][0])
        if len(batch) < batch_limit:
            break


__all__ = [
    "ADMIN_LOG_EXPORT_BATCH_SIZE",
    "ADMIN_LOG_EXPORT_ALLOWED_ROWS",
    "AdminLogExportScope",
    "export_headers",
    "iter_admin_log_export",
]
