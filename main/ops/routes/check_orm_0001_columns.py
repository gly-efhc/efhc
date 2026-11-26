#!/usr/bin/env python3
"""Static ORM versus linear Alembic critical-column guard.

The guard intentionally avoids importing SQLAlchemy.  It is safe for the
container workdir where runtime dependencies may be absent.  It checks
the release-critical economic columns that must be represented by ORM
metadata and protected by the 0001 Alembic sanity gate.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "backend" / "app" / "models"
MIGRATION = (
    ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0001_initial_release_schema.py"
)
OUTPUT = ROOT / "reports" / "generated" / "orm_0001_columns.json"
VERSIONS = ROOT / "backend" / "migrations" / "versions"

CRITICAL_COLUMNS = [
    ("efhc_core", "users", "global_id"),
    ("efhc_core", "users", "main_balance"),
    ("efhc_core", "users", "bonus_balance"),
    ("efhc_core", "users", "available_kwh"),
    ("efhc_core", "users", "total_generated_kwh"),
    ("efhc_core", "users", "rank_position"),
    ("efhc_core", "users", "rank_score_kwh"),
    ("efhc_core", "users", "rank_calculated_at"),
    ("efhc_core", "users", "exchanged_kwh_total"),
    ("efhc_core", "users", "is_vip"),
    ("efhc_core", "users", "meta"),
    ("efhc_core", "withdraw_requests", "global_id"),
    ("efhc_core", "withdraw_requests", "amount"),
    ("efhc_core", "withdraw_requests", "status"),
    ("efhc_core", "withdraw_requests", "idempotency_key"),
    ("efhc_core", "withdraw_requests", "hold_done"),
    ("efhc_core", "withdraw_requests", "refund_done"),
    ("efhc_core", "withdraw_requests", "tx_hash"),
    ("efhc_core", "payment_intents", "global_id"),
    ("efhc_core", "payment_intents", "purpose"),
    ("efhc_core", "payment_intents", "package_id"),
    ("efhc_core", "payment_intents", "asset"),
    ("efhc_core", "payment_intents", "amount_asset_d8"),
    ("efhc_core", "payment_intents", "efhc_amount_d8"),
    ("efhc_core", "payment_intents", "status"),
    ("efhc_core", "payment_intents", "idempotency_key"),
    ("efhc_core", "payment_intents", "payload"),
    ("efhc_core", "payment_intents", "external_tx_hash"),
    ("efhc_core", "panels", "global_id"),
    ("efhc_core", "panels", "is_active"),
    ("efhc_core", "panels", "is_archived"),
    ("efhc_core", "panels", "base_gen_per_sec"),
    ("efhc_core", "panels", "generated_kwh"),
    ("efhc_core", "shop_orders", "global_id"),
    ("efhc_core", "shop_orders", "type"),
    ("efhc_core", "shop_orders", "status"),
    ("efhc_core", "shop_orders", "quantity_efhc"),
    ("efhc_core", "shop_orders", "tx_hash"),
    ("efhc_core", "shop_orders", "payment_error_log"),
    ("efhc_core", "efhc_transfers_log", "global_id"),
    ("efhc_core", "efhc_transfers_log", "amount"),
    ("efhc_core", "efhc_transfers_log", "direction"),
    ("efhc_core", "efhc_transfers_log", "balance_type"),
    ("efhc_core", "efhc_transfers_log", "reason"),
    ("efhc_core", "efhc_transfers_log", "idempotency_key"),
    ("efhc_core", "bank_balance", "key"),
    ("efhc_core", "bank_balance", "balance"),
    ("efhc_core", "wallet_bindings", "global_id"),
    ("efhc_core", "wallet_bindings", "wallet_address"),
    ("efhc_core", "tasks", "bonus_efhc"),
    ("efhc_core", "tasks", "meta"),
    ("efhc_core", "task_submissions", "bonus_amount_efhc"),
    ("efhc_core", "task_bonus_log", "amount_bonus_efhc"),
    ("efhc_core", "user_tasks_status", "task_code"),
    ("efhc_core", "task_complete_lock", "credited"),
]


def _model_columns() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    table: str | None = None
    for path in sorted(MODELS.glob("*_models.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.search(r'__tablename__\s*=\s*["\']([^"\']+)', line)
            if m:
                table = m.group(1)
                tables.setdefault(table, set())
                continue
            m = re.match(r"\s{4}([a-zA-Z_][a-zA-Z0-9_]*)\s*:", line)
            if table and m:
                tables.setdefault(table, set()).add(m.group(1))
    return tables


def main() -> int:
    models = _model_columns()
    migration_text = MIGRATION.read_text(encoding="utf-8")
    missing_model = []
    for schema, table, column in CRITICAL_COLUMNS:
        if column not in models.get(table, set()):
            missing_model.append(f"{schema}.{table}.{column}")

    active_migrations = sorted(
        path.name
        for path in VERSIONS.glob("*.py")
        if path.name != "__init__.py"
    )
    tree = ast.parse(migration_text, filename=str(MIGRATION))
    frozen_columns: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_build_release_metadata":
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if not (
                isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "sa"
                and sub.func.attr == "Table"
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and isinstance(sub.args[0].value, str)
            ):
                continue
            table_name = sub.args[0].value
            columns = frozen_columns.setdefault(table_name, set())
            for arg in sub.args[2:]:
                if not isinstance(arg, ast.Call):
                    continue
                if not (
                    isinstance(arg.func, ast.Attribute)
                    and isinstance(arg.func.value, ast.Name)
                    and arg.func.value.id == "sa"
                    and arg.func.attr == "Column"
                    and arg.args
                    and isinstance(arg.args[0], ast.Constant)
                    and isinstance(arg.args[0].value, str)
                ):
                    continue
                columns.add(arg.args[0].value)

    missing_frozen = []
    for schema, table, column in CRITICAL_COLUMNS:
        if column not in frozen_columns.get(table, set()):
            missing_frozen.append(f"{schema}.{table}.{column}")

    frozen_snapshot = (
        "RELEASE_METADATA = _build_release_metadata()" in migration_text
        and "RELEASE_METADATA.create_all" in migration_text
        and "from app." not in migration_text
    )
    release_lineage_ready = active_migrations == [
        "0001_initial_release_schema.py",
    ]
    single_release_0001 = release_lineage_ready

    result = {
        "cycle": 1773,
        "guard": "orm_0001_critical_columns",
        "critical_columns": len(CRITICAL_COLUMNS),
        "missing_model_columns": missing_model,
        "missing_frozen_snapshot_columns": missing_frozen,
        "frozen_snapshot_0001": frozen_snapshot,
        "single_release_0001": single_release_0001,
        "active_migrations": active_migrations,
    }
    result["all_required_present"] = (
        not missing_model
        and not missing_frozen
        and frozen_snapshot
        and single_release_0001
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0 if result["all_required_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
