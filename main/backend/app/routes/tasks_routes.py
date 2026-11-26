from __future__ import annotations

from typing import Any

from app.core.errors_core import EFHCError
from app.core.logging_core import get_logger
from app.deps import d8, get_db, make_etag
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.schemas.id_schemas import ApiLifetimeId
from app.services.tasks_service import (
    claim_task_bonus,
    get_task_bonus_earned_total,
    list_tasks_catalog,
    list_user_tasks,
)
from app.utils.cursor_codec import decode_cursor, encode_cursor
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskItem(BaseModel):
    id: ApiLifetimeId
    code: str
    title: str
    description: str | None = None
    bonus_efhc: str
    is_active: bool
    kind: str | None = None
    meta: dict[str, Any] | None = None


class CursorPage(BaseModel):
    items: list[TaskItem]
    next_cursor: str | None = None
    etag: str | None = None


class UserTaskItem(BaseModel):
    id: ApiLifetimeId | None
    task_id: ApiLifetimeId
    status: str
    progress: dict[str, Any] | None = None
    bonus_efhc: str
    can_claim: bool
    next_available_at: str | None = None


class UserTasksPage(BaseModel):
    items: list[UserTaskItem]
    next_cursor: str | None = None
    etag: str | None = None


class ClaimIn(BaseModel):
    task_id: ApiLifetimeId = Field(
        ...,
        ge=1,
        description="ID задания для получения бонуса",
    )


class ClaimOut(BaseModel):
    ok: bool
    global_id: str
    task_id: ApiLifetimeId
    bonus_efhc: str
    bonus_balance: str
    main_balance: str
    detail: str = "ok"


class TaskEarningsOut(BaseModel):
    total_bonus_earned: str
    bonus_asset: str = "EFHCb"
    includes_ads: bool = True


def _read_bonus_efhc(row: dict[str, Any]) -> str:
    """Read canonical bonus amount with bounded fallback."""
    value = row.get("bonus_efhc")
    return format(d8(value or 0), "f")


def _clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > 100:
        return 100
    return limit


def _decode_after_id(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        payload = decode_cursor(cursor)
        return int(payload.get("after_id"))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Некорректный cursor",
        ) from exc


@router.get(
    "/catalog",
    response_model=CursorPage,
    summary="Каталог активных заданий",
)
async def get_tasks_catalog(
    response: Response,
    cursor: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    limit = _clamp_limit(limit)
    after_id = _decode_after_id(cursor)

    try:
        items_raw, next_after_id = await list_tasks_catalog(
            db,
            after_id=after_id,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("tasks.catalog failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите попытку.",
        ) from exc

    items: list[TaskItem] = []
    for it in items_raw:
        items.append(
            TaskItem(
                id=int(it["id"]),
                code=str(it["code"]),
                title=str(it["title"]),
                description=(
                    it.get("description")
                    if it.get("description") is not None
                    else None
                ),
                bonus_efhc=_read_bonus_efhc(it),
                is_active=bool(it.get("is_active", True)),
                kind=(it.get("kind") or it.get("type") or None),
                meta=(it.get("meta") or None),
            )
        )

    next_cursor = (
        encode_cursor({"after_id": int(next_after_id)})
        if next_after_id
        else None
    )
    etag = make_etag(
        {
            "items": [it.model_dump() for it in items],
            "next_cursor": next_cursor,
        }
    )
    response.headers["ETag"] = etag

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        etag=etag,
    )


async def _build_user_tasks_page(
    response: Response,
    owner: NonFinancialReadOwner,
    cursor: str | None,
    limit: int,
    db: AsyncSession,
) -> UserTasksPage:
    limit = _clamp_limit(limit)
    after_id = _decode_after_id(cursor)

    try:
        items_raw, next_after_id = await list_user_tasks(
            db,
            global_id=owner.global_id,
            after_id=after_id,
            limit=limit,
        )
    except Exception as exc:
        logger.warning(
            "tasks.my failed global_id=%s: %s",
            owner.global_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите попытку.",
        ) from exc

    items: list[UserTaskItem] = []
    for it in items_raw:
        items.append(
            UserTaskItem(
                id=int(it["id"]) if it.get("id") else None,
                task_id=int(it["task_id"]),
                status=str(it["status"]),
                progress=(
                    it.get("progress")
                    if it.get("progress") is not None
                    else None
                ),
                bonus_efhc=_read_bonus_efhc(it),
                can_claim=bool(it.get("can_claim", False)),
                next_available_at=(
                    it.get("next_available_at").isoformat()
                    if getattr(
                        it.get("next_available_at"),
                        "isoformat",
                        None,
                    )
                    else (
                        str(it.get("next_available_at"))
                        if it.get("next_available_at") is not None
                        else None
                    )
                ),
            )
        )

    next_cursor = (
        encode_cursor({"after_id": int(next_after_id)})
        if next_after_id
        else None
    )
    etag = make_etag(
        {
            "items": [it.model_dump() for it in items],
            "next_cursor": next_cursor,
            "global_id": f"{int(owner.global_id):010d}",
        }
    )
    response.headers["ETag"] = etag

    return UserTasksPage(
        items=items,
        next_cursor=next_cursor,
        etag=etag,
    )


async def _claim_for_user(
    owner: NonFinancialReadOwner,
    payload: ClaimIn,
    db: AsyncSession,
    idempotency_key: str,
) -> ClaimOut:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Idempotency-Key header is strictly required by canon "
                "for monetary operations."
            ),
        )

    try:
        result = await claim_task_bonus(
            db,
            global_id=owner.global_id,
            task_id=int(payload.task_id),
            idempotency_key=idempotency_key.strip(),
        )
    except (EFHCError, HTTPException):
        raise
    except Exception as exc:
        logger.error(
            "tasks.claim failed global_id=%s task_id=%s: %s",
            owner.global_id,
            payload.task_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите попытку.",
        ) from exc

    return ClaimOut(
        ok=bool(result.ok),
        global_id=f"{int(result.global_id):010d}",
        task_id=int(payload.task_id),
        bonus_efhc=str(d8(getattr(result, "bonus_efhc", None))),
        bonus_balance=str(d8(result.user_bonus_balance)),
        main_balance=str(d8(result.user__main__balance)),
        detail=result.detail or "ok",
    )


@router.get(
    "/earnings/me",
    response_model=TaskEarningsOut,
    summary="Суммарно заработано EFHCb по заданиям и рекламе",
)
async def get_my_task_earnings(
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
) -> TaskEarningsOut:
    total = await get_task_bonus_earned_total(
        db,
        global_id=owner.global_id,
    )
    return TaskEarningsOut(
        total_bonus_earned=format(d8(total), "f"),
        bonus_asset="EFHCb",
        includes_ads=True,
    )


@router.get(
    "/my",
    response_model=UserTasksPage,
    summary="Мои задания и статусы",
)
async def get_my_tasks(
    response: Response,
    cursor: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> UserTasksPage:
    return await _build_user_tasks_page(
        response=response,
        owner=owner,
        cursor=cursor,
        limit=limit,
        db=db,
    )


@router.post(
    "/claim",
    response_model=ClaimOut,
    summary="Получить бонус за задание",
)
async def post_claim_my_task(
    payload: ClaimIn,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
) -> ClaimOut:
    claim_ik = (
        f"task-claim:G{int(owner.global_id):010d}:"
        f"{int(payload.task_id)}"
    )
    return await _claim_for_user(
        owner=owner,
        payload=payload,
        db=db,
        idempotency_key=claim_ik,
    )
