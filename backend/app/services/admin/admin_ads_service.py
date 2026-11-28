"""Admin → ADS service: provider config, secrets, health и audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
)
from app.integrations.ads.base import AdContext
from app.integrations.ads.registry import get_provider_adapter
from app.models.ads_models import AdAdminAuditLog, AdProviderConfig
from app.services.ads.config_service import (
    decrypt_secret_config,
    encrypt_secret_config,
    load_all_provider_configs,
    load_provider_config,
    public_admin_view,
)
from app.services.ads.provider_registry import (
    PROVIDER_DESCRIPTORS,
    get_descriptor,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ACTIVE_LANGUAGES = frozenset({"en", "ru", "uk", "de", "fr", "es", "it", "tr", "pl", "da", "hi", "id", "sw", "pt", "ko", "ja"})


def _admin_db_id(value: int) -> int:
    return cast(int, global_id_to_database(global_id_from_database(value)))


def _normalize_countries(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in values or []:
        value = str(item or "").strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("INVALID_COUNTRY_CODE")
        if value not in out:
            out.append(value)
    return out


def _normalize_languages(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in values or []:
        value = str(item or "").strip()
        if value not in ACTIVE_LANGUAGES:
            raise ValueError("INVALID_LANGUAGE_CODE")
        if value not in out:
            out.append(value)
    return out


async def _audit(
    db: AsyncSession,
    *,
    admin_global_id: int,
    provider: str,
    action: str,
    field_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    safe_meta: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("secret", "token", "password", "api_key", "credential")):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe_meta[str(key)] = value
    db.add(
        AdAdminAuditLog(
            admin_global_id=_admin_db_id(admin_global_id),
            provider=str(provider),
            field_name=field_name,
            action=str(action),
            metadata_json=safe_meta or None,
        )
    )


async def list_providers(db: AsyncSession) -> list[dict[str, Any]]:
    configs = await load_all_provider_configs(db)
    return [public_admin_view(item) for item in configs]


async def get_provider(db: AsyncSession, code: str) -> dict[str, Any]:
    return cast(dict[str, Any], public_admin_view(await load_provider_config(db, code)))


async def _get_or_create_row(db: AsyncSession, code: str) -> AdProviderConfig:
    descriptor = get_descriptor(code)
    row = (
        await db.execute(select(AdProviderConfig).where(AdProviderConfig.code == descriptor.code))
    ).scalar_one_or_none()
    if row is not None:
        return row
    order = list(PROVIDER_DESCRIPTORS)
    row = AdProviderConfig(
        code=descriptor.code,
        display_name=descriptor.display_name,
        enabled=False,
        priority=order.index(descriptor.code) if descriptor.code in order else 100,
        miniapp_enabled="miniapp" in descriptor.capabilities,
        bot_enabled=False,
        rewarded_enabled="rewarded" in descriptor.capabilities,
        config_json={},
        public_config_json={},
        countries_allow=[],
        countries_block=[],
        languages_allow=[],
        languages_block=[],
        verification_mode=descriptor.verification_mode,
        verification_level=descriptor.verification_level,
        health_status="unknown",
    )
    db.add(row)
    await db.flush()
    return row


async def save_provider(
    db: AsyncSession,
    *,
    code: str,
    admin_global_id: int,
    enabled: bool | None = None,
    priority: int | None = None,
    miniapp_enabled: bool | None = None,
    bot_enabled: bool | None = None,
    rewarded_enabled: bool | None = None,
    public_config: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    countries_allow: list[str] | None = None,
    countries_block: list[str] | None = None,
    languages_allow: list[str] | None = None,
    languages_block: list[str] | None = None,
    moderation_status: str | None = None,
) -> dict[str, Any]:
    descriptor = get_descriptor(code)
    row = await _get_or_create_row(db, descriptor.code)

    if enabled is not None:
        row.enabled = bool(enabled)
    if priority is not None:
        if int(priority) < 0:
            raise ValueError("INVALID_PRIORITY")
        row.priority = int(priority)
    if miniapp_enabled is not None:
        row.miniapp_enabled = bool(miniapp_enabled)
    if bot_enabled is not None:
        row.bot_enabled = bool(bot_enabled)
    if rewarded_enabled is not None:
        row.rewarded_enabled = bool(rewarded_enabled)

    if public_config is not None:
        unknown = set(public_config).difference(descriptor.public_fields)
        if unknown:
            raise ValueError("UNKNOWN_PUBLIC_CONFIG_FIELD")
        row.public_config_json = {
            str(k): v
            for k, v in public_config.items()
            if str(v or "").strip()
        }
    if config is not None:
        # Разрешены только общие несекретные adapter options; secret-looking names запрещены.
        cleaned: dict[str, Any] = {}
        for key, value in config.items():
            name = str(key)
            lowered = name.lower()
            if any(marker in lowered for marker in ("secret", "token", "password", "api_key", "credential")):
                raise ValueError("SECRET_FIELD_REQUIRES_SECRET_ENDPOINT")
            cleaned[name] = value
        row.config_json = cleaned
    if countries_allow is not None:
        row.countries_allow = _normalize_countries(countries_allow)
    if countries_block is not None:
        row.countries_block = _normalize_countries(countries_block)
    if languages_allow is not None:
        row.languages_allow = _normalize_languages(languages_allow)
    if languages_block is not None:
        row.languages_block = _normalize_languages(languages_block)
    if moderation_status is not None:
        row.moderation_status = str(moderation_status).strip()[:32] or None

    await _audit(
        db,
        admin_global_id=admin_global_id,
        provider=descriptor.code,
        action="provider_config_saved",
    )
    await db.commit()
    return await get_provider(db, descriptor.code)


async def replace_secret(
    db: AsyncSession,
    *,
    code: str,
    field_name: str,
    value: str,
    admin_global_id: int,
) -> dict[str, Any]:
    descriptor = get_descriptor(code)
    name = str(field_name or "").strip()
    if name not in descriptor.secret_fields:
        raise ValueError("UNKNOWN_SECRET_FIELD")
    secret_value = str(value or "").strip()
    if not secret_value:
        raise ValueError("EMPTY_SECRET")
    row = await _get_or_create_row(db, descriptor.code)
    existing = decrypt_secret_config(row.secret_config_encrypted) if row.secret_config_encrypted else {}
    existing[name] = secret_value
    row.secret_config_encrypted = encrypt_secret_config(existing)
    await _audit(
        db,
        admin_global_id=admin_global_id,
        provider=descriptor.code,
        action="secret_replaced",
        field_name=name,
    )
    await db.commit()
    return await get_provider(db, descriptor.code)


async def delete_secret(
    db: AsyncSession,
    *,
    code: str,
    field_name: str,
    admin_global_id: int,
) -> dict[str, Any]:
    descriptor = get_descriptor(code)
    name = str(field_name or "").strip()
    if name not in descriptor.secret_fields:
        raise ValueError("UNKNOWN_SECRET_FIELD")
    row = await _get_or_create_row(db, descriptor.code)
    existing = decrypt_secret_config(row.secret_config_encrypted) if row.secret_config_encrypted else {}
    existing.pop(name, None)
    row.secret_config_encrypted = encrypt_secret_config(existing) if existing else None
    await _audit(
        db,
        admin_global_id=admin_global_id,
        provider=descriptor.code,
        action="secret_deleted",
        field_name=name,
    )
    await db.commit()
    return await get_provider(db, descriptor.code)


async def reset_provider_errors(
    db: AsyncSession,
    *,
    code: str,
    admin_global_id: int,
) -> dict[str, Any]:
    row = await _get_or_create_row(db, code)
    row.health_status = "unknown"
    row.last_error_at = None
    row.last_error_code = None
    await _audit(db, admin_global_id=admin_global_id, provider=code, action="errors_reset")
    await db.commit()
    return await get_provider(db, code)


async def test_provider(
    db: AsyncSession,
    *,
    code: str,
    admin_global_id: int,
    context: AdContext,
    mode: str,
) -> dict[str, Any]:
    """Configuration/SDK/request test без EFHCb reward и без ad_session payout."""

    config = await load_provider_config(db, code)
    adapter = get_provider_adapter(code)
    normalized_mode = str(mode or "configuration").strip().lower()
    configured = adapter.is_configured(config)
    eligible, reason = adapter.is_eligible(config, context, surface="miniapp")
    result: dict[str, Any] = {
        "provider": code,
        "mode": normalized_mode,
        "configured": configured,
        "eligible": eligible,
        "reason": reason,
        "verification_level": config.verification_level,
    }
    if normalized_mode == "configuration":
        pass
    elif normalized_mode == "sdk":
        if not eligible:
            result["status"] = reason or ("NOT_CONFIGURED" if not configured else "NOT_SUPPORTED")
        else:
            try:
                prepared = await adapter.prepare(
                    config,
                    context,
                    session_id=str(uuid.uuid4()),
                    task_code="admin_ads_sdk_test",
                )
            except Exception as exc:
                result["status"] = adapter.normalize_error(exc)
            else:
                result["status"] = "READY_FOR_CLIENT_SDK_TEST"
                # Только runtime-public payload. Секреты adapter использует
                # server-side и никогда не копирует в этот ответ.
                result["public_config"] = dict(prepared.public_config)
    elif normalized_mode == "request":
        if not eligible:
            result["status"] = reason or "NOT_SUPPORTED"
        else:
            try:
                prepared = await adapter.prepare(
                    config,
                    context,
                    session_id=str(uuid.uuid4()),
                    task_code="admin_ads_test",
                )
            except Exception as exc:
                result["status"] = adapter.normalize_error(exc)
            else:
                result["status"] = "HEALTHY"
                # Секреты из config сюда никогда не копируются; только публичный provider payload.
                result["public_config"] = dict(prepared.public_config)
    else:
        raise ValueError("UNKNOWN_TEST_MODE")

    row = (
        await db.execute(select(AdProviderConfig).where(AdProviderConfig.code == code))
    ).scalar_one_or_none()
    if row is not None:
        if result.get("status") in {"HEALTHY", "READY_FOR_CLIENT_SDK_TEST"} or (normalized_mode == "configuration" and configured):
            row.health_status = "healthy"
            row.last_success_at = datetime.now(tz=UTC)
            row.last_error_code = None
        elif result.get("status"):
            row.health_status = "degraded"
            row.last_error_at = datetime.now(tz=UTC)
            row.last_error_code = str(result["status"])[:64]
    await _audit(
        db,
        admin_global_id=admin_global_id,
        provider=code,
        action="provider_tested",
        metadata={"mode": normalized_mode, "status": result.get("status")},
    )
    await db.commit()
    return result


__all__ = [
    "delete_secret",
    "get_provider",
    "list_providers",
    "replace_secret",
    "reset_provider_errors",
    "save_provider",
    "test_provider",
]
