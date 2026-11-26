# backend/app/scheduler/scheduler_locks_bridge.py
# ----------------------------------------------------------------------
# Назначение кода:
# Мост для advisory-lock.
# В текущем проекте locks реализованы напрямую в job-модулях
# через SQL (pg_advisory_lock).
# ----------------------------------------------------------------------

from __future__ import annotations

# Shared lock helpers (reserved for future extensions).
