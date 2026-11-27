"""HTTP-контур единой истории профиля и серверного экспорта."""

from __future__ import annotations

import asyncio
import csv
import os
import re
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.core.database_core import db_session
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.schemas.profile_history_schemas import (
    ProfileHistoryItemOut,
    ProfileHistoryPageOut,
)
from app.services.profile_history_service import (
    PROFILE_HISTORY_EXPORT_BATCH_SIZE,
    PROFILE_HISTORY_PAGE_SIZE,
    ProfileHistoryRecord,
    list_profile_history_page,
)
from app.services.profile_history_download import ProfileExportDownloadStore
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

router = APIRouter(prefix="/profile", tags=["profile-history"])

HistoryCategory = Literal["all", "purchases", "exchange", "withdraw", "bonuses", "panels"]
_WITHDRAW_EXPORT_HEADERS = ["request_id", "created_at", "amount_efhc", "recipient_address", "status"]

_EXPORT_HEADERS = [
    "occurred_at",
    "source",
    "kind",
    "id",
    "status",
    "direction",
    "balance_type",
    "amount_efhc",
    "amount_asset",
    "asset",
    "reason",
    "recipient_address",
]
_EXPORT_MAX_ROWS = 100_000
_EXPORT_TIMEOUT_SEC = 120
_EXPORT_CONCURRENCY = asyncio.Semaphore(2)


def _wire_item(item: ProfileHistoryRecord) -> ProfileHistoryItemOut:
    return ProfileHistoryItemOut(
        id=item.id,
        source=item.source,
        kind=item.kind,
        occurred_at=item.occurred_at.astimezone(UTC).isoformat(),
        executed_at=item.executed_at.astimezone(UTC).isoformat() if item.executed_at is not None else None,
        panel_public_id=item.panel_public_id,
        status=item.status,
        direction=item.direction,
        balance_type=item.balance_type,
        amount_efhc=item.amount_efhc,
        amount_asset=item.amount_asset,
        asset=item.asset,
        reason=item.reason,
    )


@router.get(
    "/history",
    response_model=ProfileHistoryPageOut,
    summary="Единая история профиля: ровно один keyset stream по 50 операций",
)
async def profile_history(
    cursor: str | None = Query(None),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> ProfileHistoryPageOut:
    try:
        async with db_session() as db:
            page = await list_profile_history_page(
                db,
                global_id=owner.global_id,
                cursor=cursor,
                page_size=PROFILE_HISTORY_PAGE_SIZE,
                include_panel_purchases=True,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PROFILE_HISTORY_CURSOR_INVALID",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PROFILE_HISTORY_UNAVAILABLE",
        ) from exc
    return ProfileHistoryPageOut(
        items=[_wire_item(item) for item in page.items],
        next_cursor=page.next_cursor,
        page_size=PROFILE_HISTORY_PAGE_SIZE,
    )


_SIGNED_D8_RE = re.compile(r"-?[0-9]+(?:\.[0-9]{1,8})?\Z")


def _csv_safe(value: object, *, amount: bool = False) -> str:
    raw = "" if value is None else str(value)
    # Financial D8 values are legitimate signed decimals, not CSV formulas.
    # Keep them byte-for-byte; escape untrusted text and malformed amounts.
    if amount and _SIGNED_D8_RE.fullmatch(raw):
        return raw
    if raw.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + raw
    return raw


def _row_values(item: ProfileHistoryRecord, category: HistoryCategory) -> list[str]:
    if category == "withdraw":
        return [
            str(item.id),
            item.occurred_at.astimezone(UTC).isoformat(),
            item.amount_efhc or "",
            item.recipient_address or "",
            item.status or "",
        ]
    return [
        item.occurred_at.astimezone(UTC).isoformat(),
        item.source,
        item.kind,
        str(item.id),
        item.status or "",
        item.direction or "",
        item.balance_type or "",
        item.amount_efhc or "",
        item.amount_asset or "",
        item.asset or "",
        item.reason or "",
        item.recipient_address or "",
    ]


async def _history_batches(
    global_id: int,
    category: HistoryCategory,
) -> AsyncIterator[list[list[str]]]:
    """Читать историю page-by-page, закрывая DB session до file I/O."""
    cursor: str | None = None
    seen: set[str] = set()
    exported = 0
    while True:
        async with db_session() as db:
            page = await list_profile_history_page(
                db,
                global_id=global_id,
                cursor=cursor,
                page_size=PROFILE_HISTORY_EXPORT_BATCH_SIZE,
                category=category,
            )
        amount_columns = {2} if category == "withdraw" else {7, 8}
        batch = [
            [
                _csv_safe(value, amount=index in amount_columns)
                for index, value in enumerate(_row_values(item, category))
            ]
            for item in page.items
        ]
        exported += len(batch)
        if exported > _EXPORT_MAX_ROWS:
            raise RuntimeError("PROFILE_HISTORY_EXPORT_ROW_LIMIT")
        if batch:
            yield batch
        next_cursor = page.next_cursor
        if not next_cursor:
            break
        if next_cursor in seen:
            raise RuntimeError("PROFILE_HISTORY_EXPORT_CURSOR_LOOP")
        seen.add(next_cursor)
        cursor = next_cursor


def _delete_temp_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _make_temp_path(suffix: str) -> Path:
    fd, name = tempfile.mkstemp(prefix="efhc_history_", suffix=suffix)
    os.close(fd)
    return Path(name)


def _write_csv_header(path: Path, category: HistoryCategory) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(_WITHDRAW_EXPORT_HEADERS if category == "withdraw" else _EXPORT_HEADERS)


def _append_csv_batch(path: Path, batch: list[list[str]]) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerows(batch)


async def _build_csv_export(global_id: int, category: HistoryCategory) -> Path:
    path: Path | None = None
    async with _EXPORT_CONCURRENCY:
        try:
            async with asyncio.timeout(_EXPORT_TIMEOUT_SEC):
                path = await asyncio.to_thread(_make_temp_path, ".csv")
                await asyncio.to_thread(_write_csv_header, path, category)
                async for batch in _history_batches(global_id, category):
                    await asyncio.to_thread(_append_csv_batch, path, batch)
                return path
        except BaseException:
            if path is not None:
                await asyncio.to_thread(path.unlink, missing_ok=True)
            raise


@router.get("/history/export.csv", summary="CSV export общей истории профиля")
async def profile_history_csv(
    category: HistoryCategory = Query("all"),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> FileResponse:
    try:
        path = await _build_csv_export(owner.global_id, category)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PROFILE_HISTORY_EXPORT_UNAVAILABLE",
        ) from exc
    day = datetime.now(UTC).date().isoformat()
    return FileResponse(
        path=path,
        media_type="text/csv; charset=utf-8",
        filename=f"EFHC_{category}_{day}.csv",
        background=BackgroundTask(_delete_temp_file, str(path)),
    )


def _create_xlsx_book(category: HistoryCategory) -> tuple[Any, Any]:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("XLSX_EXPORT_UNAVAILABLE") from exc
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Operations")
    sheet.append(_WITHDRAW_EXPORT_HEADERS if category == "withdraw" else _EXPORT_HEADERS)
    return workbook, sheet


def _append_xlsx_batch(sheet: Any, batch: list[list[str]]) -> None:
    for row in batch:
        sheet.append(row)


async def _build_xlsx_export(global_id: int, category: HistoryCategory) -> Path:
    path: Path | None = None
    async with _EXPORT_CONCURRENCY:
        try:
            async with asyncio.timeout(_EXPORT_TIMEOUT_SEC):
                path = await asyncio.to_thread(_make_temp_path, ".xlsx")
                workbook, sheet = await asyncio.to_thread(_create_xlsx_book, category)
                async for batch in _history_batches(global_id, category):
                    await asyncio.to_thread(
                        _append_xlsx_batch,
                        sheet,
                        batch,
                    )
                await asyncio.to_thread(workbook.save, path)
                return path
        except BaseException:
            if path is not None:
                await asyncio.to_thread(path.unlink, missing_ok=True)
            raise


@router.get("/history/export.xlsx", summary="XLSX export общей истории профиля")
async def profile_history_xlsx(
    category: HistoryCategory = Query("all"),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> FileResponse:
    try:
        path = await _build_xlsx_export(owner.global_id, category)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="XLSX_EXPORT_UNAVAILABLE",
        ) from exc
    day = datetime.now(UTC).date().isoformat()
    return FileResponse(
        path=path,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        filename=f"EFHC_{category}_{day}.xlsx",
        background=BackgroundTask(_delete_temp_file, str(path)),
    )

_PROFILE_EXPORT_DOWNLOADS = ProfileExportDownloadStore()
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/history/export-ticket", summary="Prepare one private profile history download")
async def profile_history_export_ticket(
    format: Literal["csv", "xlsx"] = Query(...),
    category: HistoryCategory = Query("all"),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> JSONResponse:
    path: Path | None = None
    try:
        path = await (_build_csv_export(owner.global_id, category)
                      if format == "csv" else _build_xlsx_export(owner.global_id, category))
        day = datetime.now(UTC).date().isoformat()
        filename = f"EFHC_{category}_{day}.{format}"
        media_type = "text/csv; charset=utf-8" if format == "csv" else _XLSX_MEDIA_TYPE
        ticket = _PROFILE_EXPORT_DOWNLOADS.issue(path, filename, media_type)
    except Exception as exc:
        if path is not None:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="PROFILE_HISTORY_EXPORT_UNAVAILABLE") from exc
    return JSONResponse(
        {"ticket": ticket, "filename": filename},
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )


async def _close_profile_export(handle) -> None:
    handle.close()


@router.get("/history/export-download", summary="Redeem one private profile history download")
@router.head("/history/export-download", include_in_schema=False)
async def profile_history_export_download(
    request: Request,
    ticket: str = Query(..., min_length=43, max_length=43),
) -> Response:
    grant = (_PROFILE_EXPORT_DOWNLOADS.lookup(ticket) if request.method == "HEAD"
             else _PROFILE_EXPORT_DOWNLOADS.redeem(ticket))
    if grant is None:
        raise HTTPException(status_code=404, detail="PROFILE_HISTORY_DOWNLOAD_UNAVAILABLE",
                            headers={"Cache-Control": "private, no-store"})
    headers = {
        "Content-Disposition": f'attachment; filename="{grant.filename}"',
        "Content-Length": str(grant.size),
        "Content-Type": grant.media_type,
        "Cache-Control": "private, no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Access-Control-Allow-Origin": "https://web.telegram.org",
        "Accept-Ranges": "none",
    }
    if request.method == "HEAD":
        return Response(headers=headers)

    # Open before yielding to the ASGI server. On the Linux runtime an open
    # descriptor remains readable if expiry unlinks the temporary pathname.
    try:
        handle = grant.path.open("rb")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="PROFILE_HISTORY_DOWNLOAD_UNAVAILABLE",
                            headers={"Cache-Control": "private, no-store"}) from exc

    async def stream() -> AsyncIterator[bytes]:
        try:
            while chunk := await asyncio.to_thread(handle.read, 65536):
                yield chunk
        finally:
            handle.close()

    return StreamingResponse(stream(), headers=headers,
                             background=BackgroundTask(_close_profile_export, handle))


__all__ = ["router"]
