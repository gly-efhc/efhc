# backend/app/crud/tasks_crud.py
# ======================================================================
# Назначение кода:
# CRUD-слой БД для модуля «Задания» (tasks) и «Отправки выполнения»
# (task_submissions).
# Даёт безопасные операции создания/чтения/обновления/списков с
# курсорной
# пагинацией,
# индикаторы выполнения и утилиты для сервисного слоя (лимиты, поиск
# дублей).
#
# Канон/инварианты (важно):
# • Денежных операций здесь НЕТ. Любые выплаты EFHC — только через
# единый
# банковский сервис.
# • Идемпотентность выплат/денег обеспечивается на уровне
# services/tasks_service.py.
# • Списки ТОЛЬКО с курсорной пагинацией (без OFFSET) по (id ASC) —
# масштабируемо и устойчиво.
#
# ИИ-защита/надёжность:
# • Любые IntegrityError (например, попытка создать дубликат)
# трансформируются
# в понятные ValueError.
# • Методы поиска/листинга не «падают» на пустых результатах —
# возвращают
# корректные типы.
# • CRUD остаётся тонким и детерминированным: сложная логика и ретраи —
# в
# сервисе.
#
# Запреты:
# • Нельзя изменять балансы, начислять/списывать EFHC — только факты
# заданий и
# отправок.
# • Никакого P2P, никаких дневных ставок — логика выплат вне этого слоя.
# ======================================================================

from __future__ import annotations

from app.core.logging_core import get_logger
from app.deps import (
    decode_cursor,
    encode_cursor,
)

# единые курсоры (id, tie)
from app.models.tasks_models import Task, TaskSubmission
from sqlalchemy import Select, and_, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# ======================================================================
# ВНУТРЕННИЕ УТИЛИТЫ (минимум и без «магии»)
# ======================================================================


def _apply_task_filters(
    q: Select,
    *,
    active: bool | None,
    qtext: str | None,
) -> Select:
    """Фильтры задач: active и поиск по title/description."""
    conds = []
    if active is not None:
        conds.append(Task.active == active)
    if qtext:
        like = f"%{qtext.strip()}%"
        title_like = func.lower(Task.title).like(func.lower(like))
        desc_like = func.lower(Task.description).like(func.lower(like))
        conds.append(title_like | desc_like)
    if conds:
        q = q.where(and_(*conds))
    return q


def _apply_submission_filters(
    q: Select,
    *,
    task_id: int | None,
    user_global_id: int | None,
    status: str | None,
) -> Select:
    """Фильтры отправок: task_id/user_global_id/status."""
    conds = []
    if task_id is not None:
        conds.append(TaskSubmission.task_id == task_id)
    if user_global_id is not None:
        conds.append(TaskSubmission.global_id == user_global_id)
    if status is not None:
        conds.append(TaskSubmission.status == status)
    if conds:
        q = q.where(and_(*conds))
    return q


# ======================================================================
# TASKS — создание/чтение/изменение/удаление
# ======================================================================


async def create_task(db: AsyncSession, data: dict) -> Task:
    """
    Создать задачу.
    Исключения:
      • ValueError — при нарушении ограничений уникальности.
        Или валидации (перевод из IntegrityError).
    """
    obj = Task(**data)
    try:
        async with db.begin_nested():
            db.add(obj)
            await db.flush()
    except IntegrityError as e:
        raise ValueError(
            "Task create failed: integrity violation"
        ) from e
    return obj


async def update_task(
    db: AsyncSession,
    task_id: int,
    data: dict,
) -> Task | None:
    """
    Обновить существующую задачу.
    Возвращает объект или None, если не найден.
    """
    res = await db.execute(select(Task).where(Task.id == task_id))
    obj: Task | None = res.scalar_one_or_none()
    if not obj:
        return None

    try:
        async with db.begin_nested():
            for k, v in data.items():
                setattr(obj, k, v)
            await db.flush()
    except IntegrityError as e:
        raise ValueError(
            "Task update failed: integrity violation"
        ) from e
    return obj


async def delete_task(
    db: AsyncSession,
    task_id: int,
    *,
    safe: bool = True,
) -> bool:
    """
    Удалить задачу.
    Если safe=True — не удаляем, когда есть связанные отправки.
    Минимальная защита от потери истории.
    Возвращает True если что-то удалено.
    """
    if safe:
        # Быстрая проверка связей
        q = select(func.count(TaskSubmission.id)).where(
            TaskSubmission.task_id == task_id
        )
        cnt = (await db.execute(q)).scalar_one()
        if cnt and int(cnt) > 0:
            raise ValueError(
                "Cannot delete task with submissions (safe mode)."
            )

    res = await db.execute(
        delete(Task).where(Task.id == task_id).returning(Task.id)
    )
    return res.scalar_one_or_none() is not None


async def get_task(db: AsyncSession, task_id: int) -> Task | None:
    """Получить задачу по id или None."""
    res = await db.execute(select(Task).where(Task.id == task_id))
    return res.scalar_one_or_none()


async def get_task_by_code(
    db: AsyncSession,
    code: str,
) -> Task | None:
    """Получить задачу по уникальному коду или None."""
    res = await db.execute(select(Task).where(Task.code == code))
    return res.scalar_one_or_none()


# ======================================================================
# TASKS — курсорная пагинация списков
# ======================================================================


async def list_tasks_cursor(
    db: AsyncSession,
    *,
    active: bool | None = None,
    qtext: str | None = None,
    limit: int = 50,
    next_cursor: str | None = None,
) -> tuple[list[Task], str | None]:
    """
    Вернуть порцию задач курсором по (id ASC). Без OFFSET.
    Возвращает (items, next_cursor).
    next_cursor=None, если дальше нет данных.
    """
    limit = max(1, min(int(limit), 200))

    after_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw = payload.get("after_id")
        after_id = int(raw) if raw is not None else None

    stmt: Select = select(Task)
    stmt = _apply_task_filters(
        stmt,
        active=active,
        qtext=qtext,
    )

    if after_id is not None:
        stmt = stmt.where(Task.id > after_id)

    stmt = stmt.order_by(Task.id.asc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].id)})
    return list(rows), nxt


# Утилита для админских панелей (агрегатная статистика)
async def count_tasks_total_and_active(
    db: AsyncSession,
) -> tuple[int, int]:
    """Вернуть (total, active) по задачам."""
    q_total = select(func.count(Task.id))
    total = (await db.execute(q_total)).scalar_one() or 0
    q_active = select(func.count(Task.id)).where(Task.active.is_(True))
    active = (await db.execute(q_active)).scalar_one() or 0
    return int(total), int(active)


# ======================================================================
# TASKS — счётчик «выполнено»
# ======================================================================


async def increment_task_performed(
    db: AsyncSession,
    task_id: int,
    delta: int = 1,
) -> None:
    """
    Инкрементировать поле performed_count у задачи.
    Вызов безопасен из сервисного слоя.
    После успешной модерации (CLAIMED).
    """
    await db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(performed_count=Task.performed_count + int(delta))
    )


# ======================================================================
# SUBMISSIONS — создание/чтение/обновление статуса
# ======================================================================


async def create_submission(
    db: AsyncSession,
    *,
    task_id: int,
    user_global_id: int,
    proof_text: str | None,
    proof_url: str | None,
) -> TaskSubmission:
    """
    Создать отправку выполнения.
    Начальный статус — 'pending'. Денежных побочных эффектов НЕТ.
    """
    obj = TaskSubmission(
        task_id=int(task_id),
        global_id=int(user_global_id),
        proof_text=proof_text,
        proof_url=proof_url,
        status="pending",
    )
    try:
        async with db.begin_nested():
            db.add(obj)
            await db.flush()
    except IntegrityError as e:
        # Expected conflict откатывает только savepoint, не root transaction.
        raise ValueError(
            "Submission create failed: possibly duplicate for this"
            " task/user"
        ) from e
    return obj


async def get_submission(
    db: AsyncSession,
    submission_id: int,
) -> TaskSubmission | None:
    """Получить отправку по id или None."""
    res = await db.execute(
        select(TaskSubmission).where(TaskSubmission.id == submission_id)
    )
    return res.scalar_one_or_none()


async def get_submission_by_task_user(
    db: AsyncSession,
    *,
    task_id: int,
    user_global_id: int,
) -> TaskSubmission | None:
    """Вернуть отправку по canonical owner.

    Ключ поиска: ``task_id + user_global_id``.
    """
    res = await db.execute(
        select(TaskSubmission)
        .where(TaskSubmission.task_id == int(task_id))
        .where(TaskSubmission.global_id == int(user_global_id))
        .order_by(TaskSubmission.id.asc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def set_submission_status(
    db: AsyncSession,
    *,
    submission_id: int,
    status: str,
    # Decimal|None — сумма фиксируется сервисом при approve
    bonus_amount_efhc,
    paid: bool,
    paid_tx_id: int | None,
    moderator_global_id: int | None,
) -> TaskSubmission | None:
    """
    Универсальный апдейт статуса отправки.
    Сервис может переводить:
    pending→claiming→claimed или pending→rejected.
    Денежных операций тут нет — только фиксация фактов (paid, tx_id).
    """
    obj = await get_submission(db, submission_id)
    if not obj:
        return None

    obj.status = str(status)
    obj.bonus_amount_efhc = bonus_amount_efhc
    obj.paid = bool(paid)
    obj.paid_tx_id = paid_tx_id
    obj.moderator_global_id = moderator_global_id

    await db.flush()
    return obj


# ======================================================================
# SUBMISSIONS — курсорные списки
# ======================================================================


async def list_submissions_cursor(
    db: AsyncSession,
    *,
    task_id: int | None = None,
    user_global_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    next_cursor: str | None = None,
) -> tuple[list[TaskSubmission], str | None]:
    """
    Вернуть порцию отправок с курсорной пагинацией по (id ASC).
    """
    limit = max(1, min(int(limit), 200))

    after_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw = payload.get("after_id")
        after_id = int(raw) if raw is not None else None

    stmt: Select = select(TaskSubmission)
    stmt = _apply_submission_filters(
        stmt,
        task_id=task_id,
        user_global_id=user_global_id,
        status=status,
    )
    if after_id is not None:
        stmt = stmt.where(TaskSubmission.id > after_id)
    stmt = stmt.order_by(TaskSubmission.id.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].id)})
    return list(rows), nxt


# ======================================================================
# SUBMISSIONS — утилиты для лимитов
# ======================================================================


async def count_user_submissions_for_task(
    db: AsyncSession,
    *,
    task_id: int,
    user_global_id: int,
) -> int:
    """
    Сколько раз пользователь уже отправлял выполнение по задаче.
    Полезно для контроля limit_per_user на уровне сервиса.
    """
    val = (
        await db.execute(
            select(func.count(TaskSubmission.id))
            .where(TaskSubmission.task_id == int(task_id))
            .where(TaskSubmission.global_id == int(user_global_id))
        )
    ).scalar_one()
    return int(val or 0)


async def count_total_submissions_for_task(
    db: AsyncSession,
    *,
    task_id: int,
) -> int:
    """
    Сколько отправок уже есть по задаче.
    Для контроля total_limit на уровне сервиса.
    """
    q = select(func.count(TaskSubmission.id)).where(
        TaskSubmission.task_id == int(task_id)
    )
    val = (await db.execute(q)).scalar_one()
    return int(val or 0)


# ======================================================================
# Пояснения (для разработчиков/ревью):
# • CRUD сознательно «тонкий»: без бизнес-логики выплат/лимитов — это
# делает
# tasks_service.
# • Все листинги используют курсор по id ASC
# (encode_cursor/decode_cursor из
# deps.py).
# • set_submission_status — универсальный апдейт, безопасно меняет
# только поля
# отправки.
# • Везде, где может произойти IntegrityError, возвращаем ValueError с
# понятным
# текстом.
# • Сервисные операции (CLAIMING→CLAIMED, выплаты EFHC через банк)
# строятся
# поверх этих примитивов.
# ======================================================================
