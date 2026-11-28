# backend/app/routes/admin_logs_routes.py
# ======================================================================
# Админские логи EFHC Bot.
#
# UI:
# GET /admin/logs/transfers принимает:
# global_id, reason, limit и cursor.
# - Task service traces are visible to admins through reason=task_bonus
#   transfer-log filtering, not through a public /tasks history surface.
#
# Канон:
# - require_admin
# - курсорная пагинация (SSOT encode_cursor/decode_cursor)
# ======================================================================

from __future__ import annotations

import asyncio
import csv
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.core.utils_core import format_decimal_str
from app.deps import d8, decode_cursor_or_400, get_db, require_admin
from app.identity.api_contract import ApiExternalGlobalId
from app.models.transactions_models import EfhcTransferLog
from app.schemas.id_schemas import ApiLifetimeId
from app.services.admin.admin_log_export_service import (
    AdminLogExportScope,
    export_headers,
    iter_admin_log_export,
)
from app.utils.cursor_codec import encode_cursor
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

router = APIRouter(prefix="/admin/logs", tags=["admin:logs"])


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    if dt is None:
        return ""
    return str(dt)


def _parse_iso_dt(value: str) -> datetime:
    # decode_cursor хранит dt как isoformat().
    # Вариант с "Z" допускаем.
    s = (value or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail="cursor created_at invalid",
        ) from err


class TransferLogItem(BaseModel):
    id: ApiLifetimeId
    global_id: ApiExternalGlobalId | None
    system_entity: str | None
    amount: str
    direction: str
    balance_type: str
    reason: str
    idempotency_key: str
    meta: Any | None = None
    created_at: str


class TransferLogsOut(BaseModel):
    ok: bool = True
    items: list[TransferLogItem] = Field(default_factory=list)
    next_cursor: str | None = None


@router.get("/transfers", response_model=TransferLogsOut)
async def admin_logs_transfers(
    global_id: ApiExternalGlobalId | None = Query(default=None),
    reason: str = Query(default="", max_length=64),
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=512),
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> TransferLogsOut:
    reason_s = (reason or "").strip()

    params_limit = int(limit) + 1

    filters = []

    if global_id is not None:
        filters.append(EfhcTransferLog.global_id == int(global_id))

    if reason_s:
        filters.append(EfhcTransferLog.reason.ilike(f"%{reason_s}%"))

    if cursor:
        payload = decode_cursor_or_400(cursor)
        c_created = payload.get("created_at")
        c_id = payload.get("id")
        if not c_created or c_id is None:
            raise HTTPException(
                status_code=400,
                detail="cursor payload missing created_at/id",
            )
        dt = _parse_iso_dt(str(c_created))
        filters.append(
            tuple_(EfhcTransferLog.created_at, EfhcTransferLog.id)
            < tuple_(literal(dt), literal(int(c_id)))
        )

    stmt = (
        select(
            EfhcTransferLog.id,
            EfhcTransferLog.global_id,
            EfhcTransferLog.system_entity,
            EfhcTransferLog.amount,
            EfhcTransferLog.direction,
            EfhcTransferLog.balance_type,
            EfhcTransferLog.reason,
            EfhcTransferLog.idempotency_key,
            EfhcTransferLog.meta,
            EfhcTransferLog.created_at,
        )
        .order_by(
            desc(EfhcTransferLog.created_at),
            desc(EfhcTransferLog.id),
        )
        .limit(params_limit)
    )

    if filters:
        stmt = stmt.where(and_(*filters))

    r = await db.execute(stmt)
    rows = r.all()

    items: list[TransferLogItem] = []
    next_cursor: str | None = None

    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(
            {
                "created_at": _iso(last.created_at),
                "id": int(last.id),
            }
        )

    for row in rows:
        items.append(
            TransferLogItem(
                id=int(row.id),
                global_id=(
                    f"{int(row.global_id):010d}"
                    if row.global_id is not None
                    else None
                ),
                system_entity=(
                    str(row.system_entity)
                    if row.system_entity is not None
                    else None
                ),
                amount=format_decimal_str(d8(row.amount)),
                direction=str(row.direction),
                balance_type=str(row.balance_type),
                reason=str(row.reason),
                idempotency_key=str(row.idempotency_key),
                meta=row.meta,
                created_at=_iso(row.created_at),
            )
        )

    return TransferLogsOut(
        ok=True,
        items=items,
        next_cursor=next_cursor,
    )

_ADMIN_EXPORT_TIMEOUT_SEC = 900
_ADMIN_EXPORT_CONCURRENCY = asyncio.Semaphore(2)

AdminLogExportRows = Literal["100", "1000", "100000", "1000000", "all"]


def _export_row_limit(rows: AdminLogExportRows) -> int | None:
    if rows == "all":
        return None
    return int(rows)



def _csv_safe(value: object) -> str:
    text_value = str(value if value is not None else "")
    if text_value.startswith(("=", "+", "-", "@")):
        return "'" + text_value
    return text_value


def _delete_export(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _make_export_path(suffix: str) -> Path:
    fd, name = tempfile.mkstemp(prefix="efhc_admin_log_", suffix=suffix)
    os.close(fd)
    return Path(name)


async def _build_admin_csv(scope: AdminLogExportScope, *, row_limit: int | None) -> Path:
    path: Path | None = None
    async with _ADMIN_EXPORT_CONCURRENCY:
        try:
            async with asyncio.timeout(_ADMIN_EXPORT_TIMEOUT_SEC):
                path = await asyncio.to_thread(
                    _make_export_path, ".csv"
                )
                with path.open(
                    "w", encoding="utf-8-sig", newline=""
                ) as handle:
                    csv.writer(handle, lineterminator="\r\n").writerow(
                        export_headers(scope)
                    )
                async for batch in iter_admin_log_export(scope, row_limit=row_limit):
                    safe_batch = [
                        [_csv_safe(value) for value in row]
                        for row in batch
                    ]
                    with path.open(
                        "a", encoding="utf-8", newline=""
                    ) as handle:
                        csv.writer(
                            handle, lineterminator="\r\n"
                        ).writerows(safe_batch)
                return path
        except BaseException:
            if path is not None:
                await asyncio.to_thread(path.unlink, missing_ok=True)
            raise


def _create_admin_xlsx(scope: AdminLogExportScope) -> tuple[Any, Any]:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("ADMIN_LOG_XLSX_UNAVAILABLE") from exc
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(
        "Bank" if scope == "bank" else "Panels"
    )
    sheet.append(export_headers(scope))
    return workbook, sheet


async def _build_admin_xlsx(scope: AdminLogExportScope, *, row_limit: int | None) -> Path:
    path: Path | None = None
    async with _ADMIN_EXPORT_CONCURRENCY:
        try:
            async with asyncio.timeout(_ADMIN_EXPORT_TIMEOUT_SEC):
                path = await asyncio.to_thread(
                    _make_export_path, ".xlsx"
                )
                workbook, sheet = await asyncio.to_thread(
                    _create_admin_xlsx, scope
                )
                async for batch in iter_admin_log_export(scope, row_limit=row_limit):
                    for row in batch:
                        sheet.append(
                            [_csv_safe(value) for value in row]
                        )
                await asyncio.to_thread(workbook.save, path)
                return path
        except BaseException:
            if path is not None:
                await asyncio.to_thread(path.unlink, missing_ok=True)
            raise


@router.get(
    "/export.csv",
    summary="CSV export журнала Банка или Панелей",
)
async def admin_logs_export_csv(
    scope: Literal["bank", "panels"] = Query(...),
    rows: AdminLogExportRows = Query(default="100000"),
    ctx=Depends(require_admin),
) -> FileResponse:
    try:
        path = await _build_admin_csv(scope, row_limit=_export_row_limit(rows))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_LOG_EXPORT_UNAVAILABLE",
        ) from exc
    day = datetime.now(UTC).date().isoformat()
    return FileResponse(
        path=path,
        media_type="text/csv; charset=utf-8",
        filename=f"EFHC_{scope}_log_{day}.csv",
        background=BackgroundTask(_delete_export, str(path)),
    )


@router.get(
    "/export.xlsx",
    summary="XLSX export журнала Банка или Панелей",
)
async def admin_logs_export_xlsx(
    scope: Literal["bank", "panels"] = Query(...),
    rows: AdminLogExportRows = Query(default="100000"),
    ctx=Depends(require_admin),
) -> FileResponse:
    try:
        path = await _build_admin_xlsx(scope, row_limit=_export_row_limit(rows))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_LOG_EXPORT_UNAVAILABLE",
        ) from exc
    day = datetime.now(UTC).date().isoformat()
    return FileResponse(
        path=path,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        filename=f"EFHC_{scope}_log_{day}.xlsx",
        background=BackgroundTask(_delete_export, str(path)),
    )

