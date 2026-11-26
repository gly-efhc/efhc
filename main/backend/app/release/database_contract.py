"""Canonical production database contract derived from ORM metadata."""

from __future__ import annotations

import importlib
import pkgutil

from app import models as models_pkg
from app.models.base import Base

EXPECTED_SCHEMAS = frozenset({"efhc_core", "efhc_admin"})
EXPECTED_TABLE_COUNT = 53
ALEMBIC_SCHEMA = "efhc_core"
ALEMBIC_TABLE = "alembic_version"


def load_all_models() -> None:
    """Import every model module before reading ``Base.metadata``."""
    prefix = models_pkg.__name__ + "."
    for item in pkgutil.walk_packages(
        models_pkg.__path__,
        prefix,
    ):
        importlib.import_module(item.name)


def expected_tables() -> frozenset[tuple[str, str]]:
    """Return the exact schema/table set required by production."""
    load_all_models()
    tables = {
        (str(table.schema or ""), str(table.name))
        for table in Base.metadata.sorted_tables
        if table.schema in EXPECTED_SCHEMAS
    }
    if len(tables) != EXPECTED_TABLE_COUNT:
        raise RuntimeError(
            "ORM database contract mismatch: expected "
            f"{EXPECTED_TABLE_COUNT}, got {len(tables)}"
        )
    return frozenset(tables)


__all__ = [
    "ALEMBIC_SCHEMA",
    "ALEMBIC_TABLE",
    "EXPECTED_SCHEMAS",
    "EXPECTED_TABLE_COUNT",
    "expected_tables",
    "load_all_models",
]
