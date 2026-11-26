"""One-shot clean database migration, validation and seeding."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from app.release.database_validation import validate_database
from app.release.initial_data import (
    seed_initial_data,
    validate_initial_data,
)


def _upgrade_head() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option(
        "script_location",
        str(backend_dir / "migrations"),
    )
    command.upgrade(cfg, "head")


def main() -> int:
    print("EFHC database bootstrap: migration start")
    _upgrade_head()
    print(validate_database())
    print(seed_initial_data())
    print(validate_initial_data())
    print(validate_database())
    print("EFHC database bootstrap: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
