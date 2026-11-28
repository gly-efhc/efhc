# backend/app/services/scheduler_service.py
# ======================================================================
# Назначение кода:
# Централизованный планировщик фоновых задач EFHC Bot.
#
# Канон/инварианты:
# • Единый ритм: автоцикл каждые 10 минут (или иной INTERVAL_SEC).
# • Время — триггер пробуждения, НЕ фильтр данных.
# (обрабатываем «всё незавершённое», а не «за последние Х минут»).
# • Денежная логика вне планировщика.
#   Планировщик только вызывает run_once() у задач.
# у задач, а идемпотентность обеспечивается БД/сервисами.
#
# Serverless (Vercel) важное:
# • В Serverless НЕЛЬЗЯ запускать while True внутри HTTP-обработчика.
# • Поэтому у нас два режима:
# 1) VPS: start() запускает вечный цикл.
# 2) Serverless: /cron/tick вызывает run_single_tick() (один проход).
# • Предохранитель: при SERVERLESS=true вызов start() запрещён.
#
# ИИ-защита/самовосстановление:
# • Каждая задача выполняется с таймаутом.
# • Ошибки логируются и не роняют тик.
# • После ошибок применяется backoff (до BACKOFF_MAX_SEC).
# • Параллелизм ограничен MAX_PARALLEL_TASKS.
# ======================================================================

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from app.core.async_tasks import create_logged_task
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger("efhc.scheduler")

# Тип сигнатуры выполняемой корутины: async def job() -> Any
JobCallable = Callable[[], Awaitable[Any]]


# ----------------------------------------------------------------------
# Настройки планировщика (через .env)
# ----------------------------------------------------------------------


class SchedulerSettings(BaseSettings):
    """Настройки планировщика (через env).

    Поддерживаются два имени переменной окружения на ключ:
    базовое и с префиксом SCHED_. Это удобно для Vercel.

    Пример:
      • SERVERLESS=true
      • TASK_TIMEOUT_SEC=8 или SCHED_TASK_TIMEOUT_SEC=8
      • MAX_PARALLEL_TASKS=2 или SCHED_MAX_PARALLEL_TASKS=2
      • INTERVAL_SEC=600 или SCHED_INTERVAL_SEC=600

    Примечание:
      • env_prefix='SCHED_' не используем намеренно.
        Читаем оба варианта через validation_alias.
    """

    SERVERLESS: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "SERVERLESS",
            "SCHED_SERVERLESS",
        ),
    )

    INTERVAL_SEC: int = Field(
        default=600,
        ge=1,
        le=86400,
        validation_alias=AliasChoices(
            "INTERVAL_SEC",
            "SCHED_INTERVAL_SEC",
        ),
        description="Интервал будильника (сек)",
    )

    TASK_TIMEOUT_SEC: int = Field(
        default=300,
        ge=1,
        le=86400,
        validation_alias=AliasChoices(
            "TASK_TIMEOUT_SEC",
            "SCHED_TASK_TIMEOUT_SEC",
        ),
        description="Таймаут одной задачи (сек)",
    )

    BACKOFF_START_SEC: int = Field(
        default=5,
        ge=1,
        le=3600,
        validation_alias=AliasChoices(
            "BACKOFF_START_SEC",
            "SCHED_BACKOFF_START_SEC",
        ),
    )

    BACKOFF_MAX_SEC: int = Field(
        default=300,
        ge=1,
        le=86400,
        validation_alias=AliasChoices(
            "BACKOFF_MAX_SEC",
            "SCHED_BACKOFF_MAX_SEC",
        ),
    )

    MAX_PARALLEL_TASKS: int = Field(
        default=3,
        ge=1,
        le=64,
        validation_alias=AliasChoices(
            "MAX_PARALLEL_TASKS",
            "SCHED_MAX_PARALLEL_TASKS",
        ),
    )

    JITTER_SEC: int = Field(
        default=7,
        ge=0,
        le=3600,
        validation_alias=AliasChoices(
            "JITTER_SEC",
            "SCHED_JITTER_SEC",
        ),
    )

    HEALTH_FILE: str = Field(
        default="/app/runtime/scheduler_health.json",
        validation_alias=AliasChoices(
            "HEALTH_FILE",
            "SCHEDULER_HEALTH_FILE",
            "SCHED_HEALTH_FILE",
        ),
    )

    HEALTH_MAX_AGE_SEC: int = Field(
        default=900,
        ge=1,
        le=86400,
        validation_alias=AliasChoices(
            "HEALTH_MAX_AGE_SEC",
            "SCHEDULER_HEALTH_MAX_AGE_SEC",
            "SCHED_HEALTH_MAX_AGE_SEC",
        ),
    )

    # Канонический «единый тик» = 10 минут. Можно менять через env.
    model_config = SettingsConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _validate_backoff_order(self) -> SchedulerSettings:
        """Максимальный backoff не может быть меньше начального."""
        if self.BACKOFF_MAX_SEC < self.BACKOFF_START_SEC:
            raise ValueError(
                "BACKOFF_MAX_SEC должен быть >= BACKOFF_START_SEC"
            )
        return self


SETTINGS = SchedulerSettings()


# ----------------------------------------------------------------------
# Мягкие импорты задач (если модуля нет — задача будет скипаться)
# ----------------------------------------------------------------------


def _soft_import(path: str, name: str) -> Any:
    """Импорт: если модуля нет — возвращает None (задача скипается)."""
    try:
        module = __import__(path, fromlist=[name])
        return getattr(module, name)
    except Exception as e:  # pragma: no cover
        logger.debug("soft import failed: %s.%s -> %s", path, name, e)
        return None


# Сервисы-исполнители «единичных» тиков (каждые 10 минут)
energy_backfill_once = _soft_import(
    "app.scheduler.generate_energy",
    "run_once",
)
ton_inbox_run_once = _soft_import(
    "app.scheduler.check_ton_inbox",
    "run_once",
)
vip_check_run_once = _soft_import(
    "app.scheduler.check_vip_nft",
    "run_once",
)
archive_panels_run_once = _soft_import(
    "app.scheduler.archive_panels",
    "run_once",
)
update_ranks_run_once = _soft_import(
    "app.scheduler.update_ranks",
    "run_once",
)
tasks_autorestart_run_once = _soft_import(
    "app.scheduler.tasks_autorestart",
    "run_once",
)
ads_rotation_run_once = _soft_import(
    "app.scheduler.ads_rotation",
    "run_once",
)
ads_reward_reconciliation_run_once = _soft_import(
    "app.scheduler.ads_reward_reconciliation",
    "run_once",
)
ads_revenue_importer_run_once = _soft_import(
    "app.scheduler.ads_revenue_importer",
    "run_once",
)
reports_daily_run_once = _soft_import(
    "app.scheduler.reports_daily",
    "run_once",
)
financial_retention_run_once = _soft_import(
    "app.scheduler.financial_retention",
    "run_once",
)


def _utcnow() -> datetime:
    """Служебная функция планировщика."""
    return cast(datetime, utcnow())


# ----------------------------------------------------------------------
# DailyGate — разовая «ежедневная» отработка внутри
# 10‑минутного цикла
# ----------------------------------------------------------------------
@dataclass
class DailyGate:
    """Запускает job не чаще 1 раза в window (обычно 24 ч)."""

    window: timedelta = field(default=timedelta(hours=24))
    last_run_at: datetime | None = None

    def due(self, now: datetime | None = None) -> bool:
        """Служебная функция планировщика."""
        now = now or _utcnow()
        if self.last_run_at is None:
            return True
        return (now - self.last_run_at) >= self.window

    def mark(self, now: datetime | None = None) -> None:
        """Служебная функция планировщика."""
        self.last_run_at = now or _utcnow()


# ----------------------------------------------------------------------
# Структуры задач
# ----------------------------------------------------------------------
@dataclass
class _Job:
    name: str
    factory: Callable[[], JobCallable]
    daily_gate: DailyGate | None = None
    backoff_sec: int = field(
        default_factory=lambda: int(SETTINGS.BACKOFF_START_SEC),
    )
    consecutive_failures: int = 0
    last_error: str | None = None
    running: bool = False
    next_allowed_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_duration_ms: int | None = None
    last_result: Any | None = None


# ----------------------------------------------------------------------
# Планировщик
# ----------------------------------------------------------------------


class SchedulerService:
    """Централизованный планировщик с единым будильником."""

    def __init__(self, settings: SchedulerSettings = SETTINGS):
        """Create an idle scheduler service."""
        self.s = settings
        self._jobs: dict[str, _Job] = {}
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._main_task: asyncio.Task[None] | None = None
        max_parallel = int(self.s.MAX_PARALLEL_TASKS or 1)
        max_parallel = max(1, max_parallel)
        self._sem = asyncio.Semaphore(max_parallel)

    @property
    def registered_job_names(self) -> tuple[str, ...]:
        """Return the exact registered production job set."""
        return tuple(self._jobs.keys())

    # -------------------------- Регистрация --------------------------

    def register_defaults(self, *, strict: bool = False) -> None:
        """Register every canonical EFHC background job.

        Production uses ``strict=True`` so a missing job entry fails
        startup instead of silently disabling automation.
        """

        def _factory_or_skip(
            callable_ref: JobCallable | None,
            label: str,
        ) -> Callable[[], JobCallable]:
            """Служебная функция планировщика."""

            async def _noop() -> dict[str, Any]:
                """Служебная функция планировщика."""
                logger.warning("%s unavailable — skip", label)
                return {"skipped": True, "reason": "unavailable"}

            async def _wrap() -> Any:
                """Служебная функция планировщика."""
                return await callable_ref()  # type: ignore[misc]

            if callable_ref is None:
                if strict:
                    raise RuntimeError(
                        f"required scheduler job unavailable: {label}"
                    )
                return lambda: _noop
            return lambda: _wrap

        # Ежедневная: reports_daily (через DailyGate).
        # Остальное — каждый тик.
        self._add_job(
            "generate_energy",
            _factory_or_skip(
                energy_backfill_once,
                "generate_energy",
            ),
        )
        self._add_job(
            "check_ton_inbox",
            _factory_or_skip(
                ton_inbox_run_once,
                "check_ton_inbox",
            ),
        )
        self._add_job(
            "check_vip_nft",
            _factory_or_skip(
                vip_check_run_once,
                "check_vip_nft",
            ),
        )
        self._add_job(
            "archive_panels",
            _factory_or_skip(
                archive_panels_run_once,
                "archive_panels",
            ),
        )
        self._add_job(
            "update_ranks",
            _factory_or_skip(
                update_ranks_run_once,
                "update_ranks",
            ),
        )
        self._add_job(
            "tasks_autorestart",
            _factory_or_skip(
                tasks_autorestart_run_once,
                "tasks_autorestart",
            ),
        )
        self._add_job(
            "ads_rotation",
            _factory_or_skip(
                ads_rotation_run_once,
                "ads_rotation",
            ),
        )
        self._add_job(
            "ads_reward_reconciliation",
            _factory_or_skip(
                ads_reward_reconciliation_run_once,
                "ads_reward_reconciliation",
            ),
        )
        self._add_job(
            "ads_revenue_importer",
            _factory_or_skip(
                ads_revenue_importer_run_once,
                "ads_revenue_importer",
            ),
            daily=True,
        )
        self._add_job(
            "reports_daily",
            _factory_or_skip(
                reports_daily_run_once,
                "reports_daily",
            ),
            daily=True,
        )
        self._add_job(
            "financial_retention",
            _factory_or_skip(
                financial_retention_run_once,
                "financial_retention",
            ),
            daily=True,
        )

        logger.info(
            "Scheduler: registered jobs: %s",
            list(self._jobs.keys()),
        )

    def _add_job(
        self,
        name: str,
        factory: Callable[[], JobCallable],
        daily: bool = False,
    ) -> None:
        """Служебная функция планировщика."""
        if name in self._jobs:
            raise ValueError(f"job '{name}' already registered")
        self._jobs[name] = _Job(
            name=name,
            factory=factory,
            daily_gate=(DailyGate() if daily else None),
            backoff_sec=int(self.s.BACKOFF_START_SEC),
        )

    # ------------------------- Жизненный цикл ------------------------

    async def start(self) -> asyncio.Task[None]:
        """Start the long-running VPS scheduler exactly once."""
        if bool(self.s.SERVERLESS):
            raise RuntimeError(
                "SERVERLESS=true: use run_single_tick() instead"
            )
        if not self._jobs:
            raise RuntimeError("scheduler has no registered jobs")

        async with self._lock:
            if self._main_task is not None:
                if not self._main_task.done():
                    return self._main_task
                self._main_task = None
            self._stop.clear()
            logger.info(
                (
                    "Scheduler: start (%d jobs, interval=%ss, "
                    "timeout=%ss, max_parallel=%s)"
                ),
                len(self._jobs),
                self.s.INTERVAL_SEC,
                self.s.TASK_TIMEOUT_SEC,
                self.s.MAX_PARALLEL_TASKS,
            )
            self._write_health(
                status="starting",
                payload={"jobs": list(self._jobs)},
            )
            self._main_task = create_logged_task(
                self._loop(),
                name="scheduler:main",
            )
            return self._main_task

    async def stop(self, *, timeout_sec: float = 30.0) -> None:
        """Request shutdown and await the main loop.

        A stuck job is cancelled after the bounded grace period so
        container termination cannot hang indefinitely.
        """
        self._stop.set()
        task = self._main_task
        if task is None:
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=max(0.1, timeout_sec),
            )
        except TimeoutError:
            logger.error(
                "scheduler shutdown timed out after %ss; cancelling",
                timeout_sec,
            )
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        finally:
            self._main_task = None

    async def run_single_tick(self) -> dict[str, Any]:
        """Один проход тика (для Serverless /cron/tick)."""
        return await self._run_tick()

    # ------------------------------ Цикл -----------------------------

    async def _loop(self) -> None:
        """Служебная функция планировщика."""
        while not self._stop.is_set():
            try:
                tick = await self._run_tick()
                self._write_health(
                    status=(
                        "ready"
                        if tick.get("status") == "ok"
                        else "degraded"
                    ),
                    payload=tick,
                )
            except Exception as e:  # pragma: no cover
                logger.exception("Scheduler loop error: %s", e)
                self._write_health(
                    status="error",
                    payload={"error": str(e)},
                )

            # Интервал сна (с джиттером) — только в VPS-режиме.
            sleep_sec = int(self.s.INTERVAL_SEC)
            if int(self.s.JITTER_SEC) > 0:
                # «джиттер» без random: доля текущего времени,
                # чтобы не будить все инстансы строго одновременно.
                # не зависеть от глобального генератора.
                now_ms = int(_utcnow().timestamp() * 1000)
                jitter = now_ms % (int(self.s.JITTER_SEC) + 1)
                sleep_sec = max(0, sleep_sec - jitter)

            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=float(sleep_sec),
                )
            except TimeoutError:
                continue

    # --------------------------- Исполнение тика ----------------------

    async def _run_tick(self) -> dict[str, Any]:
        """Служебная функция планировщика."""
        started_at = _utcnow()
        due_jobs = []

        now = started_at
        for job in self._jobs.values():
            # DailyGate
            gate_due = True
            if job.daily_gate is not None:
                gate_due = job.daily_gate.due(now)
            if not gate_due:
                continue
            # Backoff
            if job.next_allowed_at is not None and (
                now < job.next_allowed_at
            ):
                continue
            due_jobs.append(job)

        results: dict[str, Any] = {}
        ok = 0
        failed = 0
        skipped = 0

        async def _runner(j: _Job) -> None:
            """Служебная функция планировщика."""
            nonlocal ok, failed, skipped
            async with self._sem:
                out = await self._run_job(j)
            results[j.name] = out
            if out.get("status") == "ok":
                ok += 1
            elif out.get("status") == "skipped":
                skipped += 1
            else:
                failed += 1

        runners = [_runner(j) for j in due_jobs]
        await asyncio.gather(*runners, return_exceptions=False)

        finished_at = _utcnow()
        delta = finished_at - started_at
        duration_ms = int(delta.total_seconds() * 1000)

        return {
            "status": "ok" if failed == 0 else "partial",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "jobs_total": len(self._jobs),
            "jobs_due": len(due_jobs),
            "jobs_ok": ok,
            "jobs_failed": failed,
            "jobs_skipped": skipped,
            "jobs": results,
        }

    async def _run_job(self, job: _Job) -> dict[str, Any]:
        """Служебная функция планировщика."""
        if job.running:
            return {"status": "skipped", "reason": "already_running"}

        job.running = True
        job.last_started_at = _utcnow()

        t0 = asyncio.get_event_loop().time()
        try:
            coro = job.factory()()
            res = await asyncio.wait_for(
                coro,
                timeout=float(self.s.TASK_TIMEOUT_SEC),
            )

            job.consecutive_failures = 0
            job.last_error = None
            job.backoff_sec = int(self.s.BACKOFF_START_SEC)
            job.next_allowed_at = None
            job.last_result = res

            if job.daily_gate is not None:
                job.daily_gate.mark(_utcnow())

            status = "ok"
            detail = None
            if isinstance(res, dict):
                result_status = str(res.get("status") or "ok")
                if result_status in {
                    "error",
                    "failed",
                    "partial",
                    "timeout_error",
                }:
                    status = "error"
                    detail = str(
                        res.get("error_text")
                        or res.get("detail")
                        or result_status
                    )
                    job.consecutive_failures += 1
                    job.last_error = detail
                    self._apply_backoff(job)

        except TimeoutError:
            job.consecutive_failures += 1
            job.last_error = "timeout"
            self._apply_backoff(job)
            status = "error"
            detail = "timeout"

        except Exception as e:
            job.consecutive_failures += 1
            job.last_error = str(e)
            self._apply_backoff(job)
            logger.exception("Job '%s' failed: %s", job.name, e)
            status = "error"
            detail = str(e)

        finally:
            t1 = asyncio.get_event_loop().time()
            job.last_duration_ms = int((t1 - t0) * 1000)
            job.last_finished_at = _utcnow()
            job.running = False

        return {
            "status": status,
            "duration_ms": job.last_duration_ms,
            "failures": job.consecutive_failures,
            "next_allowed_at": (
                job.next_allowed_at.isoformat()
                if job.next_allowed_at
                else None
            ),
            "detail": detail,
            "result": job.last_result if status == "ok" else None,
        }

    def _write_health(
        self,
        *,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        """Atomically expose scheduler readiness without secrets."""
        path = Path(self.s.HEALTH_FILE)
        data = {
            "status": status,
            "updated_at": _utcnow().isoformat(),
            "pid": os.getpid(),
            "registered_jobs": list(self._jobs),
            "payload": payload,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        temp.replace(path)

    def _apply_backoff(self, job: _Job) -> None:
        """Экспоненциальный backoff с потолком."""
        base = int(self.s.BACKOFF_START_SEC)
        b = int(job.backoff_sec or base)
        b = max(0, b)
        max_b = int(self.s.BACKOFF_MAX_SEC)
        b = max(base, b * 2)
        b = min(max_b, b)
        job.backoff_sec = b
        job.next_allowed_at = _utcnow() + timedelta(seconds=b)


__all__ = [
    "SchedulerSettings",
    "SchedulerService",
]
