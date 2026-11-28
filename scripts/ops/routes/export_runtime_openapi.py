"""Export runtime OpenAPI with an honest dependency gate."""

from __future__ import annotations

import glob
import json
import os
import sys
import sysconfig
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "generated" / "runtime_openapi.json"
STATUS = (
    ROOT / "reports" / "generated" / "runtime_openapi_1182_status.json"
)


def _add_runtime_paths() -> None:
    candidates: set[str] = set()
    for value in sysconfig.get_paths().values():
        if "site-packages" in value or "dist-packages" in value:
            candidates.add(value)
    patterns = (
        "/usr/local/lib/python*/site-packages",
        "/usr/local/lib/python*/dist-packages",
        "/usr/lib/python*/site-packages",
        "/usr/lib/python*/dist-packages",
    )
    for pattern in patterns:
        candidates.update(glob.glob(pattern))
    for path in sorted(candidates):
        if path not in sys.path and Path(path).exists():
            sys.path.append(path)


def _prepare_env() -> None:
    os.environ.setdefault("ENV", "local")
    os.environ.setdefault("SERVERLESS", "true")
    os.environ.setdefault("ALLOW_REAL_FUNDS", "false")
    os.environ.setdefault("ALLOW_INSECURE_USER_HEADERS", "false")


def _write_status(status: str, detail: str, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "status": status,
        "detail": detail,
        "output": str(OUT.relative_to(ROOT)),
    }
    payload.update(extra)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    _add_runtime_paths()
    _prepare_env()
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.main import app  # type: ignore
    except ModuleNotFoundError as exc:
        _write_status(
            "blocked_missing_dependency",
            f"{exc.name}: {exc}",
            missing_dependency=exc.name,
            python_executable=sys.executable,
            sys_path=sys.path,
        )
        return 2
    except Exception as exc:
        _write_status(
            "blocked_runtime_import",
            f"{type(exc).__name__}: {exc}",
        )
        return 3
    try:
        schema: dict[str, Any] = app.openapi()
    except Exception as exc:
        _write_status(
            "blocked_openapi_call",
            f"{type(exc).__name__}: {exc}",
        )
        return 4
    paths = schema.get("paths", {})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_status("ok", f"paths={len(paths)}", path_count=len(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
