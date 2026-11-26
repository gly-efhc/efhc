# backend/app/scheduler/scheduler_registry.py
# ======================================================================
# Назначение кода:
# Реестр job-функций. В serverless (Vercel) используется единый «тик».
# ======================================================================

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

JobFn = Callable[[], Awaitable[None]]


@dataclass
class JobSpec:
    name: str
    fn: JobFn


class JobRegistry:
    def __init__(self) -> None:
        """Создаёт пустой реестр job-функций планировщика."""
        self._jobs: dict[str, JobSpec] = {}

    def register(self, name: str, fn: JobFn) -> None:
        """Регистрирует job-функцию по имени."""
        self._jobs[name] = JobSpec(name=name, fn=fn)

    def all(self) -> list[JobSpec]:
        """Возвращает список job-описаний в порядке регистрации."""
        return list(self._jobs.values())
