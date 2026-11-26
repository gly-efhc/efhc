"""Статическое сравнение ORM и frozen snapshot миграции 0001.

Guard не импортирует SQLAlchemy или приложение. Он fail-closed проверяет, что
единственный release-head самодостаточен: physical schema заморожена внутри
0001, не зависит от ``app.models`` и совпадает с текущим pre-release ORM по
таблицам, физическим колонкам и module-level indexes.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "backend" / "app" / "models"
MIG = ROOT / "backend" / "migrations" / "versions" / "0001_initial_release_schema.py"
OUT = ROOT / "reports" / "generated" / "orm_0001_compare.json"


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _model_contract() -> tuple[dict[str, set[str]], set[str]]:
    tables: dict[str, set[str]] = {}
    module_indexes: set[str] = set()
    for path in sorted(MODEL_DIR.glob("*_models.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if (
                    _call_name(call) == "Index"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)
                ):
                    module_indexes.add(call.args[0].value)
            if not isinstance(node, ast.ClassDef):
                continue
            table: str | None = None
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "__tablename__"
                    for target in stmt.targets
                ):
                    continue
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    table = stmt.value.value
                    break
            if table is None:
                continue
            columns: set[str] = set()
            for stmt in node.body:
                attr_name: str | None = None
                value: ast.expr | None = None
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    attr_name, value = stmt.target.id, stmt.value
                elif (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                ):
                    attr_name, value = stmt.targets[0].id, stmt.value
                if not attr_name or not isinstance(value, ast.Call):
                    continue
                if _call_name(value) not in {"mapped_column", "Column"}:
                    continue
                db_name = attr_name
                if (
                    value.args
                    and isinstance(value.args[0], ast.Constant)
                    and isinstance(value.args[0].value, str)
                ):
                    db_name = value.args[0].value
                columns.add(db_name)
            if any(isinstance(base, ast.Name) and base.id == "TimestampMixin" for base in node.bases):
                columns.update({"created_at", "updated_at"})
            tables[table] = columns
    return tables, module_indexes


def _migration_contract() -> tuple[dict[tuple[str, str], set[str]], set[str], list[str]]:
    tree = ast.parse(MIG.read_text(encoding="utf-8"), filename=str(MIG))
    app_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app"):
            app_imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app"):
                    app_imports.append(alias.name)

    tables: dict[tuple[str, str], set[str]] = {}
    indexes: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_build_release_metadata":
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            name = _call_name(sub)
            if (
                name == "Index"
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and isinstance(sub.args[0].value, str)
            ):
                indexes.add(sub.args[0].value)
            if name != "Table" or not sub.args or not isinstance(sub.args[0], ast.Constant):
                continue
            table = sub.args[0].value
            if not isinstance(table, str):
                continue
            schema: str | None = None
            for keyword in sub.keywords:
                if (
                    keyword.arg == "schema"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    schema = keyword.value.value
            if schema is None:
                continue
            columns: set[str] = set()
            for arg in sub.args[2:]:
                if not isinstance(arg, ast.Call) or _call_name(arg) != "Column":
                    continue
                if arg.args and isinstance(arg.args[0], ast.Constant) and isinstance(arg.args[0].value, str):
                    columns.add(arg.args[0].value)
            tables[(schema, table)] = columns
    return tables, indexes, sorted(set(app_imports))


def main() -> int:
    model_tables, model_module_indexes = _model_contract()
    frozen_tables, frozen_indexes, app_imports = _migration_contract()
    migration = MIG.read_text(encoding="utf-8")
    frozen_by_name = {table: columns for (_schema, table), columns in frozen_tables.items()}
    missing_tables = sorted(set(model_tables) - set(frozen_by_name))
    extra_tables = sorted(set(frozen_by_name) - set(model_tables))
    column_drift: dict[str, dict[str, list[str]]] = {}
    for table in sorted(set(model_tables) & set(frozen_by_name)):
        missing = sorted(model_tables[table] - frozen_by_name[table])
        extra = sorted(frozen_by_name[table] - model_tables[table])
        if missing or extra:
            column_drift[table] = {"missing": missing, "extra": extra}
    missing_module_indexes = sorted(model_module_indexes - frozen_indexes)
    schema_counts = {
        schema: sum(1 for item_schema, _table in frozen_tables if item_schema == schema)
        for schema in {schema for schema, _table in frozen_tables}
    }
    frozen_anchor = (
        "RELEASE_METADATA = _build_release_metadata()" in migration
        and "RELEASE_METADATA.create_all" in migration
    )
    passed = (
        frozen_anchor
        and not app_imports
        and not missing_tables
        and not extra_tables
        and not column_drift
        and not missing_module_indexes
        and len(frozen_tables) == 53
        and schema_counts == {"efhc_core": 46, "efhc_admin": 7}
    )
    data = {
        "guard": "orm_0001_frozen_snapshot",
        "cycle": 1773,
        "model_table_count": len(model_tables),
        "frozen_table_count": len(frozen_tables),
        "missing_from_frozen_snapshot": missing_tables,
        "extra_in_frozen_snapshot": extra_tables,
        "column_drift": column_drift,
        "model_module_index_count": len(model_module_indexes),
        "frozen_index_name_count": len(frozen_indexes),
        "missing_module_indexes": missing_module_indexes,
        "frozen_schema_counts": schema_counts,
        "app_imports_in_0001": app_imports,
        "frozen_metadata_anchor": frozen_anchor,
        "strategy": "migration-local frozen SQLAlchemy MetaData snapshot",
        "passed": passed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
