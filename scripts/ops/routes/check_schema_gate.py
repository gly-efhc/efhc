from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "backend" / "app" / "models"
MIGRATION = ROOT / "backend" / "migrations" / "versions" / "0001_initial_release_schema.py"


def _frozen_table_count(source: str) -> int:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_release_metadata":
            return sum(
                1
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "sa"
                and sub.func.attr == "Table"
            )
    return 0


def build() -> dict[str, object]:
    tables: list[dict[str, str]] = []
    pattern = r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]"
    for file_path in sorted(MODELS.glob("*_models.py")):
        text = file_path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(pattern, text):
            tables.append({"file": str(file_path.relative_to(ROOT)), "table": match.group(1)})
    migration_text = MIGRATION.read_text(encoding="utf-8", errors="replace")
    frozen = (
        "RELEASE_METADATA = _build_release_metadata()" in migration_text
        and "RELEASE_METADATA.create_all" in migration_text
        and "from app." not in migration_text
    )
    return {
        "model_table_count": len(tables),
        "frozen_table_count": _frozen_table_count(migration_text),
        "self_contained_frozen_0001": frozen,
        "migration_file": str(MIGRATION.relative_to(ROOT)),
        "tables": tables,
        "boundary": "field-level proof remains DB-backed; static parity has a separate guard",
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
