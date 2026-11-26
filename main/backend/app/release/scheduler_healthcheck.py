"""Docker healthcheck for the standalone scheduler container."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    path = Path(
        os.getenv(
            "SCHEDULER_HEALTH_FILE",
            "/app/runtime/scheduler_health.json",
        )
    )
    max_age = int(
        os.getenv("SCHEDULER_HEALTH_MAX_AGE_SEC", "900")
    )
    if not path.is_file():
        print("scheduler health file is missing")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        status = str(data.get("status") or "")
        updated = datetime.fromisoformat(str(data["updated_at"]))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - updated).total_seconds()
    except Exception as exc:
        print(f"invalid scheduler health file: {exc}")
        return 1
    if status not in {"ready", "degraded"}:
        print(f"scheduler status is not ready: {status}")
        return 1
    if age > max_age:
        print(f"scheduler health is stale: {age:.1f}s")
        return 1
    print(f"scheduler health ok: {status}, age={age:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
