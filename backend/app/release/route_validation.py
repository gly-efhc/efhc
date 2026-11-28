"""Validate mandatory production routes without starting the server."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from app.main import app

MANDATORY_PATH_FRAGMENTS = (
    "/api/tg/webhook",
    "/api/health",
    "/meta/health_db",
    "/api/admin/shop",
    "/api/admin/hub",
    "/api/ranks",
)


def _legacy_route_paths(routes: Iterable[object]) -> set[str]:
    """Collect paths for FastAPI releases with a flat route list."""
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        nested = getattr(route, "routes", None)
        if isinstance(nested, Iterable) and not isinstance(
            nested,
            (str, bytes),
        ):
            paths.update(_legacy_route_paths(nested))
    return paths


def collect_route_paths(routes: Sequence[Any]) -> set[str]:
    """Return effective paths across flat and nested FastAPI routers.

    FastAPI 0.137+ keeps included routers as route-tree nodes. The
    public ``iter_route_contexts`` API exposes the effective path after
    all include-router prefixes are applied. Older supported releases
    expose a flat route list, handled by the compatibility fallback.
    """
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        return _legacy_route_paths(routes)

    paths: set[str] = set()
    for context in iter_route_contexts(routes):
        path = context.path
        if isinstance(path, str):
            paths.add(path)
    return paths


def validate_routes() -> dict[str, object]:
    paths = collect_route_paths(app.routes)
    missing = [
        item
        for item in MANDATORY_PATH_FRAGMENTS
        if not any(path.startswith(item) for path in paths)
    ]
    if missing:
        raise RuntimeError(
            "Mandatory production routes are missing: "
            + ", ".join(missing)
        )
    return {
        "route_count": len(paths),
        "mandatory": list(MANDATORY_PATH_FRAGMENTS),
        "status": "ok",
    }


def main() -> int:
    print(validate_routes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
