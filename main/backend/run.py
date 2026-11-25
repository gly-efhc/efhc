"""EFHC production runner.

Runs the FastAPI server and the canonical SchedulerService in one
process. Business logic remains in application services and scheduler
jobs; this module only owns process lifecycle and graceful shutdown.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from contextlib import suppress
from typing import Final

import uvicorn
from app.core.async_tasks import create_logged_task
from app.core.config_core import get_settings
from app.core.database_core import db_ping
from app.core.logging_core import get_logger
from app.core.system_locks import assert_system_locks
from app.services.scheduler_service import SchedulerService

logger = get_logger(__name__)
settings = get_settings()

API_HOST: Final[str] = os.getenv("API_HOST", "0.0.0.0")
API_PORT: Final[int] = int(os.getenv("API_PORT", "8000"))
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "info").lower()
SCHEDULER_ENABLED: Final[bool] = (
    os.getenv("SCHEDULER_ENABLED", "true").lower()
    not in {"0", "false", "no"}
)
SHUTDOWN_TIMEOUT_SEC: Final[float] = float(
    os.getenv("SHUTDOWN_TIMEOUT_SEC", "45")
)


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    stop_event: asyncio.Event,
) -> None:
    """Request graceful shutdown on SIGINT or SIGTERM."""

    def _request_stop(sig_name: str) -> None:
        logger.info("signal: %s received, shutting down", sig_name)
        stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        if not hasattr(signal, sig_name):
            continue
        sig = getattr(signal, sig_name)
        with suppress(NotImplementedError):
            loop.add_signal_handler(
                sig,
                _request_stop,
                sig_name,
            )


async def _lightweight_db_ping() -> None:
    """Проверить DB preflight через canonical database API."""
    ok = await db_ping()
    if ok:
        logger.info("db ping: OK")
        return
    if settings.env_normalized in {"prod", "stage"}:
        raise RuntimeError("database preflight failed")
    logger.warning("db ping failed in local/dev/ci")


async def preflight_checks() -> None:
    """Validate architectural locks and basic database reachability."""
    assert_system_locks()
    await _lightweight_db_ping()


def _build_server() -> uvicorn.Server:
    """Build the production Uvicorn server instance."""
    config = uvicorn.Config(
        app="app.main:app",
        host=API_HOST,
        port=API_PORT,
        log_level=LOG_LEVEL,
        proxy_headers=True,
        forwarded_allow_ips="*",
        reload=False,
        loop="asyncio",
        timeout_keep_alive=30,
    )
    return uvicorn.Server(config)


async def _stop_scheduler(scheduler: SchedulerService | None) -> None:
    """Stop and await the scheduler within the shutdown budget."""
    if scheduler is None:
        return
    try:
        await scheduler.stop(timeout_sec=SHUTDOWN_TIMEOUT_SEC)
    except Exception:
        logger.exception("scheduler shutdown failed")
        raise


async def run_all() -> int:
    """Run API and the canonical scheduler until signal or API exit."""
    await preflight_checks()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    _install_signal_handlers(loop, stop_event)

    server = _build_server()
    scheduler: SchedulerService | None = None
    scheduler_task: asyncio.Task[None] | None = None

    if SCHEDULER_ENABLED:
        scheduler = SchedulerService()
        scheduler.register_defaults(strict=True)
        scheduler_task = await scheduler.start()
        logger.info(
            "scheduler enabled with jobs=%s",
            scheduler.registered_job_names,
        )
    else:
        logger.info("scheduler disabled by SCHEDULER_ENABLED")

    api_task = create_logged_task(
        server.serve(),
        name="uvicorn-server",
    )
    stop_task = create_logged_task(
        stop_event.wait(),
        name="shutdown-signal-waiter",
    )

    try:
        watched_tasks = {api_task, stop_task}
        if scheduler_task is not None:
            watched_tasks.add(scheduler_task)
        done, _ = await asyncio.wait(
            watched_tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if scheduler_task is not None and scheduler_task in done:
            scheduler_error = scheduler_task.exception()
            if scheduler_error is not None:
                raise scheduler_error
            raise RuntimeError("scheduler exited unexpectedly")
        if api_task in done:
            api_error = api_task.exception()
            if api_error is not None:
                raise api_error
            logger.warning("API server exited; stopping scheduler")
        else:
            server.should_exit = True
            await asyncio.wait_for(
                api_task,
                timeout=SHUTDOWN_TIMEOUT_SEC,
            )
    finally:
        server.should_exit = True
        stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task
        if not api_task.done():
            api_task.cancel()
            with suppress(asyncio.CancelledError):
                await api_task
        await _stop_scheduler(scheduler)

    logger.info("run_all terminated cleanly")
    return 0


async def run_api_only() -> int:
    """Run only FastAPI."""
    await preflight_checks()
    server = _build_server()
    await server.serve()
    return 0


async def run_scheduler_only() -> int:
    """Run only the canonical scheduler until SIGINT or SIGTERM."""
    await preflight_checks()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    _install_signal_handlers(loop, stop_event)

    scheduler = SchedulerService()
    scheduler.register_defaults(strict=True)
    scheduler_task = await scheduler.start()
    logger.info(
        "scheduler-only mode started with jobs=%s",
        scheduler.registered_job_names,
    )
    stop_task = create_logged_task(
        stop_event.wait(),
        name="scheduler-stop-waiter",
    )
    try:
        done, _ = await asyncio.wait(
            {scheduler_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if scheduler_task in done and not stop_event.is_set():
            error = scheduler_task.exception()
            if error is not None:
                raise error
            raise RuntimeError("scheduler exited unexpectedly")
    finally:
        stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task
        await _stop_scheduler(scheduler)
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="EFHC-runner",
        description="EFHC API and canonical scheduler runner",
    )
    parser.add_argument(
        "--mode",
        choices=("all", "api", "scheduler"),
        default="all",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = _parse_args(argv or sys.argv[1:])
    try:
        if args.mode == "api":
            return asyncio.run(run_api_only())
        if args.mode == "scheduler":
            return asyncio.run(run_scheduler_only())
        return asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("interrupted by user")
        return 130
    except Exception as exc:
        logger.exception("fatal runner error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
