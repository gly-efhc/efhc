"""Fail closed before local/staging services connect to a database."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from urllib.parse import unquote, urlsplit


def validate_deployment_environment(values: Mapping[str, str]) -> None:
    mode = values.get("EFHC_DEPLOYMENT_MODE", "production")
    if mode == "production":
        return  # Existing production preflight/config contracts remain owners.
    if mode not in {"local", "stage"}:
        raise ValueError("DEPLOYMENT_MODE_INVALID")
    if values.get("ENV") != "stage" or values.get("ALLOW_REAL_FUNDS") != \
            "false":
        raise ValueError("DEPLOYMENT_STAGE_SAFETY_INVALID")
    prefix = "efhc_local_" if mode == "local" else "efhc_stage_"
    for name in ("POSTGRES_DB", "POSTGRES_USER"):
        if not re.fullmatch(prefix + r"[a-z0-9_]+", values.get(name, "")):
            raise ValueError("DEPLOYMENT_DATABASE_IDENTITY_INVALID")
    if values.get("POSTGRES_HOST") != "db" or values.get("POSTGRES_PORT") \
            != "5432":
        raise ValueError("DEPLOYMENT_DATABASE_HOST_INVALID")
    password = values.get("POSTGRES_PASSWORD", "")
    if len(password) < 32:
        raise ValueError("DEPLOYMENT_DATABASE_SECRET_INVALID")
    for name in ("SECRET_KEY", "CRON_SECRET", "TELEGRAM_WEBHOOK_SECRET"):
        if len(values.get(name, "")) < 32:
            raise ValueError("DEPLOYMENT_SECRET_BINDING_MISSING:" + name)
    for name in ("DATABASE_URL", "SYNC_DATABASE_URL"):
        try:
            url = urlsplit(values.get(name, ""))
            matches = (
                url.scheme in {"postgresql", "postgresql+asyncpg",
                               "postgresql+psycopg"}
                and url.hostname == "db" and url.port == 5432
                and unquote(url.path.lstrip("/")) == values["POSTGRES_DB"]
                and unquote(url.username or "") == values["POSTGRES_USER"]
                and unquote(url.password or "") == password
                and not url.query and not url.fragment
            )
        except (KeyError, ValueError):
            matches = False
        if not matches:
            raise ValueError("DEPLOYMENT_DATABASE_BINDING_INVALID")
    forbidden = {
        "TON_PRIVATE_KEY", "BANK_PRIVATE_KEY", "BANK_MNEMONIC",
        "TON_MNEMONIC", "WALLET_MNEMONIC", "BANK_SEED",
    }
    if any(values.get(name) for name in forbidden):
        raise ValueError("DEPLOYMENT_TREASURY_BINDING_FORBIDDEN")


def main() -> int:
    try:
        validate_deployment_environment(os.environ)
    except ValueError as exc:
        # Stable machine codes only, never DSNs/credentials or full ENV.
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
