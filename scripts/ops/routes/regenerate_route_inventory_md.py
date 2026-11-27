from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
FREEZE = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTE_INVENTORY_FREEZE.csv"
OUT = ROOT / "docs/audits/ROUTE_INVENTORY_FREEZE.md"


def main() -> None:
    with FREEZE.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    lines = [
        "# ROUTE INVENTORY FREEZE",
        "",
        (
            "Status note: active route inventory regenerated for "
            "cycle `1688`."
        ),
        (
            "`historical route inventory snapshot` сохранён как "
            "термин совместимости."
        ),
        "",
        "Дата freeze: 2026-08-06",
        "",
        f"- Active routes in freeze: {len(rows)}",
        "- Источник истины: `docs/SSOT/ssot_pack/SSOT_ROUTES.csv`",
        (
            "- Сервисные ссылки извлекаются из "
            "`docs/SSOT/ssot_pack/SSOT_ROUTES_TABLES_MIGRATIONS.csv` "
            "(`evidence_refs`)."
        ),
        (
            "- `ROUTE_ONLY_OR_INLINE` означает: отдельный service-файл "
            "прямым доказательством не подтверждён, либо логика "
            "inline/route-only."
        ),
        "",
        "## Колонки freeze",
        "",
        "- `method`",
        "- `path`",
        "- `file`",
        "- `router_module`",
        "- `prefix`",
        "- `service_refs`",
        "- `auth_type`",
        "",
        "## Inventory",
        "",
        "| # | method | path | file | prefix | "
        "service_refs | auth_type |",
        "|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"| {idx} | {row['method']} | `{row['path']}` | "
            f"`{row['file']}` | `{row['prefix']}` | "
            f"`{row['service_refs']}` | `{row['auth_type']}` |"
        )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
