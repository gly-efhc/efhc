"""Provider-independent PostgreSQL connection helpers."""

from __future__ import annotations

import os
from typing import Any

import psycopg2


def connection_kwargs(
    *,
    database_name: str | None = None,
) -> dict[str, Any]:
    """Build safe libpq keyword arguments from production ENV."""
    return {
        "host": os.getenv("POSTGRES_HOST", "db"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": database_name
        or os.environ.get("POSTGRES_DB", "efhc"),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "connect_timeout": 10,
    }


def connect(
    *,
    database_name: str | None = None,
):
    """Open a synchronous PostgreSQL connection."""
    return psycopg2.connect(
        **connection_kwargs(database_name=database_name)
    )
