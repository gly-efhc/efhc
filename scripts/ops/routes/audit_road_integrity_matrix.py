"""Build a static EFHC road-integrity inventory.

The script is intentionally lightweight. It does not replace runtime
OpenAPI generation, but it gives a fast source-level map for audits.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTE_DIR = ROOT / "backend" / "app" / "routes"
MODEL_DIR = ROOT / "backend" / "app" / "models"
ALEMBIC_DIR = ROOT / "backend" / "alembic"
FRONTEND_DIR = ROOT / "frontend"

ROUTE_RE = re.compile(
    r"@(?P<router>\w+)\.(?P<method>get|post|put|patch|delete)"
    r"\(\s*[\"'](?P<path>[^\"']+)[\"']"
)
TABLE_RE = re.compile(r"__tablename__\s*=\s*[\"']([^\"']+)[\"']")
CREATE_RE = re.compile(r"op\.create_table\(\s*[\"']([^\"']+)[\"']")
API_RE = re.compile(r"[\"'](/[^\"'\s<>]+)[\"']")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def py_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    return sorted(base.rglob("*.py"))


def frontend_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    suffixes = {".ts", ".tsx", ".js", ".jsx"}
    rows = []
    for p in base.rglob("*"):
        rel = str(p.relative_to(ROOT))
        if "/faq/" in rel.lower():
            continue
        if "catalogs.ts" in rel:
            continue
        if p.suffix in suffixes:
            rows.append(p)
    return sorted(rows)


def collect_routes() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in py_files(ROUTE_DIR):
        text = read_text(path)
        for match in ROUTE_RE.finditer(text):
            rows.append(
                {
                    "method": match.group("method").upper(),
                    "path": match.group("path"),
                    "file": str(path.relative_to(ROOT)),
                }
            )
    return rows


def collect_models() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in py_files(MODEL_DIR):
        text = read_text(path)
        for table in TABLE_RE.findall(text):
            rows.append(
                {
                    "table": table,
                    "file": str(path.relative_to(ROOT)),
                }
            )
    return rows


def collect_migrations() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in py_files(ALEMBIC_DIR):
        text = read_text(path)
        for table in CREATE_RE.findall(text):
            rows.append(
                {
                    "table": table,
                    "file": str(path.relative_to(ROOT)),
                }
            )
    return rows


def collect_frontend_calls() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in frontend_files(FRONTEND_DIR):
        text = read_text(path)
        for api_path in API_RE.findall(text):
            if len(api_path) < 2:
                continue
            rows.append(
                {
                    "path": api_path,
                    "file": str(path.relative_to(ROOT)),
                }
            )
    return rows


def collect_migration_strategy() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in py_files(ROOT / "backend" / "migrations"):
        text = read_text(path)
        if "Base.metadata" in text or "metadata" in text:
            rows.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "note": "metadata-driven migration file",
                }
            )
    return rows


def main() -> None:
    data = {
        "routes": collect_routes(),
        "models": collect_models(),
        "migrations": collect_migrations(),
        "migration_strategy": collect_migration_strategy(),
        "frontend_calls": collect_frontend_calls(),
    }
    output = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    print(output)


if __name__ == "__main__":
    main()
