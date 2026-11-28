# backend/app/routes/admin_tasks_routes.py
# ======================================================================
# Админские HTTP-ручки блока «Задания» (Tasks) EFHC Bot.
#
# Назначение:
# - CRUD заданий.
# - Просмотр пользовательских заявок (submissions) с курсорами.
# - Модерация заявок (approve/reject) с безопасной выплатой через банк.
#
# Канон:
# - Денежные операции требуют Idempotency-Key.
# - Денежные эффекты выполняет только банк (transactions_service).
# - Пагинация без OFFSET: только курсоры encode_cursor/decode_cursor.
# - ETag для кэша списков.
# ======================================================================

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.logging_core import get_logger
from app.deps import (
    d8,
    decode_cursor_or_400,
    get_db,
    make_etag,
    require_admin,
    require_admin_write,
)
from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.id_schemas import ApiLifetimeId
from app.utils.cursor_codec import encode_cursor
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin:tasks"],
    dependencies=[Depends(require_admin)],
)

try:
    from app.services.admin.admin_tasks_service import force_tasks_sync
except Exception:
    force_tasks_sync = None


def _etag_payload(payload: dict[str, Any]) -> str:
    """ETag хелпер для ответов (детерминированный)."""
    return str(make_etag(payload))


# ----------------------------------------------------------------------
# «Мягкие» импорты сервисов.
# Если сервис недоступен/не импортируется — возвращаем 503.
# ----------------------------------------------------------------------
TaskCodeChangeBlockedError: Any = RuntimeError
TaskDeleteBlockedError: Any = RuntimeError

try:
    from app.services.tasks_service import (  # type: ignore
        TaskCodeChangeBlockedError as _TaskCodeChangeBlockedError,
    )
    from app.services.tasks_service import (
        TaskDeleteBlockedError as _TaskDeleteBlockedError,
    )
    from app.services.tasks_service import (
        admin_create_task,
        admin_delete_task,
        admin_get_task,
        admin_list_submissions,
        admin_list_tasks,
        admin_update_task,
        moderate_submission_and_pay,
    )

    TaskCodeChangeBlockedError = _TaskCodeChangeBlockedError
    TaskDeleteBlockedError = _TaskDeleteBlockedError
    _TASK_SVC_AVAILABLE = True
except Exception:
    admin_create_task = None
    admin_update_task = None
    admin_delete_task = None
    admin_get_task = None
    admin_list_tasks = None
    admin_list_submissions = None
    moderate_submission_and_pay = None
    _TASK_SVC_AVAILABLE = False


# ----------------------------------------------------------------------
# Pydantic-схемы (локально, без зависимости от app/schemas).
# ----------------------------------------------------------------------


class TaskCreate(BaseModel):
    """Полная модель создания задания из Admin Tasks Editor."""

    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True
    bonus_efhc: str = Field(
        ...,
        description="Бонус EFHC в формате Decimal(18,8).",
    )
    kind: str = Field("custom", min_length=1, max_length=50)
    price_usd_hint: str | None = None
    limit_per_user: int = Field(1, ge=0)
    total_limit: int | None = Field(None, ge=0)
    proof_type: str | None = Field(None, max_length=50)
    proof_hint: str | None = Field(None, max_length=255)
    meta: dict[str, Any] | None = None

    @field_validator("code", "title", "kind")
    def _v_required_text(cls, v: str) -> str:
        """Убирать пробелы и запрещать пустые обязательные поля."""
        value = str(v).strip()
        if not value:
            raise ValueError("поле не может быть пустым")
        return value

    @field_validator("bonus_efhc")
    def _v_bonus(cls, v: str) -> str:
        """Валидировать положительный бонус и нормализовать к d8."""
        amt = d8(v)
        if amt <= Decimal("0"):
            raise ValueError("поле бонуса должно быть > 0")
        return str(amt)

    @field_validator("price_usd_hint")
    def _v_price(cls, v: str | None) -> str | None:
        """Валидировать необязательную подсказку стоимости в USD."""
        if v in (None, ""):
            return None
        amt = d8(v)
        if amt < Decimal("0"):
            raise ValueError("price_usd_hint должен быть >= 0")
        return str(amt)


class TaskUpdate(BaseModel):
    """Частичное редактирование canonical-модели задания."""

    code: str | None = Field(None, min_length=1, max_length=64)
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    bonus_efhc: str | None = None
    kind: str | None = Field(None, min_length=1, max_length=50)
    price_usd_hint: str | None = None
    limit_per_user: int | None = Field(None, ge=0)
    total_limit: int | None = Field(None, ge=0)
    proof_type: str | None = Field(None, max_length=50)
    proof_hint: str | None = Field(None, max_length=255)
    meta: dict[str, Any] | None = None

    @field_validator("code", "title", "kind")
    def _v_optional_text(cls, v: str | None) -> str | None:
        """Нормализовать редактируемые строковые поля."""
        if v is None:
            return None
        value = str(v).strip()
        if not value:
            raise ValueError("поле не может быть пустым")
        return value

    @field_validator("bonus_efhc")
    def _v_bonus(cls, v: str | None) -> str | None:
        """Валидировать положительный бонус и нормализовать к d8."""
        if v is None:
            return v
        amt = d8(v)
        if amt <= Decimal("0"):
            raise ValueError("поле бонуса должно быть > 0")
        return str(amt)

    @field_validator("price_usd_hint")
    def _v_price(cls, v: str | None) -> str | None:
        """Валидировать необязательную подсказку стоимости в USD."""
        if v in (None, ""):
            return None
        amt = d8(v)
        if amt < Decimal("0"):
            raise ValueError("price_usd_hint должен быть >= 0")
        return str(amt)


class TaskOut(BaseModel):
    """Полный DTO задания для многофункционального Admin Editor."""

    id: ApiLifetimeId
    code: str
    title: str
    description: str | None = None
    is_active: bool
    bonus_efhc: str
    kind: str
    price_usd_hint: str | None = None
    limit_per_user: int
    total_limit: int | None = None
    performed_count: int
    proof_type: str | None = None
    proof_hint: str | None = None
    meta: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedTasks(BaseModel):
    """Ответ со списком заданий (курсоры)."""

    items: list[TaskOut]
    next_cursor: str | None = None


class SubmissionOut(BaseModel):
    """DTO пользовательской заявки на задание."""

    id: ApiLifetimeId
    task_id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    status: str
    proof_text: str | None = None
    proof_url: str | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None
    bonus_efhc: str | None = None
    moderator_global_id: ApiExternalGlobalId | None = None
    moderator_note: str | None = None


class PaginatedSubmissions(BaseModel):
    """Ответ со списком заявок (курсоры)."""

    items: list[SubmissionOut]
    next_cursor: str | None = None


class SubmissionModerateIn(BaseModel):
    """Вход модерации: approve/reject (+опциональная ручная сумма)."""

    approve: bool
    moderator_note: str | None = Field(
        None,
        description="Комментарий модератора для аудита и уведомления.",
    )
    bonus_override_efhc: str | None = Field(
        None,
        description=(
            "Необязательная ручная сумма бонуса (строка Decimal(30,8))"
        ),
    )

    @field_validator("bonus_override_efhc")
    def _v_override(cls, v: str | None) -> str | None:
        """Валидирует bonus_override_efhc и нормализует к d8."""
        if v is None:
            return v
        amt = d8(v)
        if amt <= Decimal("0"):
            raise ValueError(
                "bonus_override_efhc должен быть > 0 (сумма бонуса)"
            )
        return str(amt)


class TasksRefreshOut(BaseModel):
    ok: bool
    detail: str
    deleted: int = 0
    retention_days: int | None = None


# ----------------------------------------------------------------------
# CRUD заданий (без прямых денежных действий)
# ----------------------------------------------------------------------


@router.post(
    "/",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_admin(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _write_auth: Any = Depends(require_admin_write),
) -> TaskOut:
    """Создать задание (денег не трогает)."""
    if not _TASK_SVC_AVAILABLE or admin_create_task is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )
    try:
        data = payload.model_dump()
        obj = await admin_create_task(db, data)
        return TaskOut(**obj)
    except HTTPException:
        raise
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Код задания уже существует или нарушено ограничение БД",
        ) from e
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("admin_create_task failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка создания задания",
        ) from e


@router.get(
    "/",
    response_model=PaginatedTasks,
)
async def list_tasks_admin(
    response: Response,
    limit: int = 50,
    cursor: str | None = None,
    q: str | None = Query(None, description="Поиск по названию"),
    active: bool | None = Query(
        None, description="Фильтр по активности"
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTasks:
    """Список заданий с курсорами + ETag."""
    if not _TASK_SVC_AVAILABLE or admin_list_tasks is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )

    after: dict[str, Any] | None = None
    if cursor:
        after = decode_cursor_or_400(cursor)

    try:
        data = await admin_list_tasks(
            db,
            limit=int(limit),
            after=after,
            q=q,
            active=active,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_list_tasks failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка списка заданий",
        ) from e

    items_raw: list[dict[str, Any]] = list(data.get("items") or [])
    items = [TaskOut(**it) for it in items_raw]
    next_after = data.get("next_after")

    next_cursor: str | None
    if next_after:
        next_cursor = encode_cursor({"after_id": int(next_after)})
    else:
        next_cursor = None

    body = PaginatedTasks(items=items, next_cursor=next_cursor)

    try:
        response.headers["ETag"] = _etag_payload(body.model_dump())
    except Exception:
        logger.warning("ETag compute failed", exc_info=True)

    return body


# ADMIN_UI_CONNECTED: detail-route используется canonical Tasks Editor
# для просмотра и редактирования выбранного задания.
@router.get(
    "/{task_id}",
    response_model=TaskOut,
)
async def get_task_admin(
    task_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    """Получить задание по ID."""
    if not _TASK_SVC_AVAILABLE or admin_get_task is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )
    try:
        obj = await admin_get_task(db, int(task_id))
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задание не найдено",
            )
        return TaskOut(**obj)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_get_task failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка получения задания",
        ) from e


@router.patch(
    "/{task_id}",
    response_model=TaskOut,
)
async def update_task_admin(
    task_id: ApiLifetimeId,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _write_auth: Any = Depends(require_admin_write),
) -> TaskOut:
    """Обновить поля задания (без выплат)."""
    if not _TASK_SVC_AVAILABLE or admin_update_task is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )
    try:
        patch = payload.model_dump(exclude_unset=True)
        obj = await admin_update_task(db, int(task_id), dict(patch))
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задание не найдено",
            )
        return TaskOut(**obj)
    except HTTPException:
        raise
    except TaskCodeChangeBlockedError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "TASK_CODE_CHANGE_BLOCKED",
                "message": (
                    "Нельзя менять code задания после появления истории. "
                    "Создайте новое задание или сначала деактивируйте текущее."
                ),
                "details": {"blockers": e.blockers},
            },
        ) from e
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Код задания уже существует или нарушено ограничение БД",
        ) from e
    except Exception as e:
        logger.exception("admin_update_task failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка обновления задания",
        ) from e


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task_admin(
    task_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    _write_auth: Any = Depends(require_admin_write),
) -> None:
    """Удалить только новое задание без submissions или runtime-истории."""
    if not _TASK_SVC_AVAILABLE or admin_delete_task is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )
    try:
        ok = await admin_delete_task(db, int(task_id))
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задание не найдено",
            )
        return None
    except HTTPException:
        raise
    except TaskDeleteBlockedError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "TASK_DELETE_BLOCKED",
                "message": (
                    "Удаление запрещено: у задания есть история. "
                    "Используйте деактивацию, чтобы сохранить аудит."
                ),
                "details": {"blockers": e.blockers},
            },
        ) from e
    except Exception as e:
        logger.exception("admin_delete_task failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка удаления задания",
        ) from e


# ----------------------------------------------------------------------
# Витрина заявок по заданию (просмотр)
# ----------------------------------------------------------------------


@router.get(
    "/{task_id}/subs",
    response_model=PaginatedSubmissions,
)
async def list_task_submissions_admin(
    response: Response,
    task_id: ApiLifetimeId,
    limit: int = 50,
    cursor: str | None = None,
    status_filter: str | None = Query(
        None,
        alias="status",
        description="PENDING/APPROVED/REJECTED",
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedSubmissions:
    """Список заявок по конкретному заданию (курсоры + ETag)."""
    if not _TASK_SVC_AVAILABLE or admin_list_submissions is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )

    after: dict[str, Any] | None = None
    if cursor:
        after = decode_cursor_or_400(cursor)

    try:
        data = await admin_list_submissions(
            db,
            task_id=int(task_id),
            limit=int(limit),
            after=after,
            status=status_filter,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_list_submissions failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка списка заявок",
        ) from e

    items_raw: list[dict[str, Any]] = list(data.get("items") or [])
    items = [SubmissionOut(**it) for it in items_raw]
    next_after = data.get("next_after")

    next_cursor: str | None
    if next_after:
        next_cursor = encode_cursor({"after_id": int(next_after)})
    else:
        next_cursor = None

    body = PaginatedSubmissions(items=items, next_cursor=next_cursor)

    try:
        response.headers["ETag"] = _etag_payload(body.model_dump())
    except Exception:
        logger.warning("ETag compute failed", exc_info=True)

    return body


@router.post(
    "/refresh-statuses",
    response_model=TasksRefreshOut,
)
async def refresh_task_statuses_admin(
    db: AsyncSession = Depends(get_db),
    _write_auth: Any = Depends(require_admin_write),
) -> TasksRefreshOut:
    """Запустить безопасное обслуживание idempotency-locks заданий."""
    if force_tasks_sync is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_tasks_service недоступен",
        )
    try:
        result = await force_tasks_sync(db)
        return TasksRefreshOut(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("refresh_task_statuses_admin failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка обслуживания задач",
        ) from e


# ----------------------------------------------------------------------
# Модерация заявки (approve/reject) + ВЫПЛАТА бонуса (денежная операция)
# ----------------------------------------------------------------------


@router.post(
    "/submissions/{submission_id}/moderate",
    response_model=SubmissionOut,
)
async def moderate_submission_admin(
    submission_id: ApiLifetimeId,
    payload: SubmissionModerateIn,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
) -> SubmissionOut:
    """Модерация заявки.

    - approve=True: выплата бонуса через банк идемпотентно.
    - approve=False: отклонение без денежных последствий.

    Требование: Idempotency-Key обязателен для денежных операций.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Idempotency-Key обязателен для денежных операций"),
        )

    if not _TASK_SVC_AVAILABLE or moderate_submission_and_pay is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tasks_service недоступен",
        )

    try:
        override: Decimal | None
        if payload.bonus_override_efhc:
            override = d8(payload.bonus_override_efhc)
        else:
            override = None

        sub = await moderate_submission_and_pay(
            db=db,
            submission_id=int(submission_id),
            approve=bool(payload.approve),
            moderator_global_id=int(auth.global_id),
            moderator_note=(payload.moderator_note or None),
            bonus_override_efhc=override,
            idempotency_key=idempotency_key.strip(),
        )
        return SubmissionOut(**sub)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("moderate_submission_and_pay failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка модерации",
        ) from e
