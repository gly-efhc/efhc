"""Static proof helper for user/profile and panels-summary roads."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
MATRIX = ROOT / "reports" / "generated" / "frontend_backend_matrix.json"
OUT = ROOT / "reports" / "generated" / "user_panels_roads.json"
TARGETS = [
    "/api/user/me",
    "/api/user/me/panels-summary",
]


def main() -> None:
    data = json.loads(MATRIX.read_text(encoding="utf-8"))
    calls = data.get("frontend_calls", [])
    backend = data.get("backend_routes", [])
    rows = []
    for target in TARGETS:
        exact_calls = [c for c in calls if c.get("path") == target]
        route_rows = [
            r for r in backend if r.get("runtime_path") == target
        ]
        rows.append(
            {
                "target": target,
                "backend_routes": route_rows,
                "frontend_exact_calls": exact_calls,
                "frontend_exact__call__count": len(exact_calls),
                "backend_route_count": len(route_rows),
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"targets": rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"targets": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
