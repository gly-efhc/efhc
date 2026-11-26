"""Fail-closed validation for the migrated EFHC production database."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.release.database_connection import connect
from app.release.database_contract import (
    ALEMBIC_SCHEMA,
    ALEMBIC_TABLE,
    EXPECTED_SCHEMAS,
    EXPECTED_TABLE_COUNT,
    expected_tables,
)


def _alembic_head() -> str:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option(
        "script_location",
        str(backend_dir / "migrations"),
    )
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            "Exactly one Alembic head is required; got "
            f"{heads!r}"
        )
    return str(heads[0])


def _fmt(items: Iterable[tuple[str, str]]) -> str:
    return ", ".join(f"{schema}.{table}" for schema, table in items)


def validate_database(
    *,
    database_name: str | None = None,
) -> dict[str, object]:
    """Validate schemas, Alembic head and all 53 ORM tables."""
    expected = expected_tables()
    with (
        connect(database_name=database_name) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname = ANY(%s)",
            (list(EXPECTED_SCHEMAS),),
        )
        actual_schemas = {str(row[0]) for row in cur.fetchall()}
        missing_schemas = EXPECTED_SCHEMAS - actual_schemas
        if missing_schemas:
            raise RuntimeError(
                "Missing database schemas: "
                + ", ".join(sorted(missing_schemas))
            )

        cur.execute(
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema = ANY(%s)",
            (list(EXPECTED_SCHEMAS),),
        )
        actual = {
            (str(schema), str(table))
            for schema, table in cur.fetchall()
        }
        actual.discard((ALEMBIC_SCHEMA, ALEMBIC_TABLE))
        missing = expected - actual
        unexpected = actual - expected
        if missing or unexpected:
            details: list[str] = []
            if missing:
                details.append("missing=" + _fmt(sorted(missing)))
            if unexpected:
                details.append(
                    "unexpected=" + _fmt(sorted(unexpected))
                )
            raise RuntimeError(
                "Database table contract mismatch: "
                + "; ".join(details)
            )
        if len(actual) != EXPECTED_TABLE_COUNT:
            raise RuntimeError(
                "Expected exactly "
                f"{EXPECTED_TABLE_COUNT} ORM tables, "
                f"got {len(actual)}"
            )

        cur.execute(
            "SELECT to_regclass(%s)",
            (f"{ALEMBIC_SCHEMA}.{ALEMBIC_TABLE}",),
        )
        if cur.fetchone()[0] is None:
            raise RuntimeError(
                "Missing efhc_core.alembic_version"
            )
        cur.execute(
            "SELECT version_num "
            "FROM efhc_core.alembic_version"
        )
        row = cur.fetchone()
        current = str(row[0]) if row else ""
        head = _alembic_head()
        if current != head:
            raise RuntimeError(
                "Alembic revision mismatch: "
                f"database={current!r}, head={head!r}"
            )

    return {
        "database": database_name or "default",
        "schemas": sorted(EXPECTED_SCHEMAS),
        "table_count": EXPECTED_TABLE_COUNT,
        "alembic_head": _alembic_head(),
        "status": "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-name", default=None)
    args = parser.parse_args()
    result = validate_database(database_name=args.database_name)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
