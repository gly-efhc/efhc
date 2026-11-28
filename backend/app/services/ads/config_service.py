"""Runtime-конфигурация ADS: Admin DB override → ENV fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.config_core import get_settings
from app.models.ads_models import AdProviderConfig
from app.services.ads.provider_registry import (
    PROVIDER_DESCRIPTORS,
    ProviderDescriptor,
)
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()


@dataclass(slots=True)
class ProviderRuntimeConfig:
    descriptor: ProviderDescriptor
    enabled: bool
    priority: int
    miniapp_enabled: bool
    bot_enabled: bool
    rewarded_enabled: bool
    public: dict[str, Any]
    secret: dict[str, str]
    countries_allow: tuple[str, ...]
    countries_block: tuple[str, ...]
    languages_allow: tuple[str, ...]
    languages_block: tuple[str, ...]
    verification_level: str
    verification_mode: str
    health_status: str
    moderation_status: str | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_code: str | None
    source: str

    @property
    def code(self) -> str:
        return str(self.descriptor.code)

    def is_configured(self) -> bool:
        for field in self.descriptor.required_public_fields:
            if not str(self.public.get(field, "") or "").strip():
                return False
        for field in self.descriptor.required_secret_fields:
            if not str(self.secret.get(field, "") or "").strip():
                return False
        return True

    def language_allowed(self, language: str) -> bool:
        lang = str(language or "en").strip()
        if self.languages_allow and lang not in self.languages_allow:
            return False
        return lang not in self.languages_block

    def country_allowed(self, country: str | None) -> bool:
        if not country:
            return True
        value = str(country).upper()
        if self.countries_allow and value not in self.countries_allow:
            return False
        return value not in self.countries_block


def _fernet() -> Fernet:
    raw = str(getattr(settings, "ADS_SECRETS_ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        raise ValueError("ADS_SECRETS_ENCRYPTION_KEY_REQUIRED")
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as exc:
        raise ValueError("ADS_SECRETS_ENCRYPTION_KEY_INVALID") from exc


def encrypt_secret_config(values: dict[str, str]) -> str:
    safe = {str(k): str(v) for k, v in values.items() if str(v).strip()}
    payload = json.dumps(safe, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_secret_config(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        payload = _fernet().decrypt(str(value).encode("ascii"))
        raw = json.loads(payload.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("ADS_SECRET_DECRYPT_FAILED") from exc
    if not isinstance(raw, dict):
        raise ValueError("ADS_SECRET_DECRYPT_FAILED")
    return {str(k): str(v) for k, v in raw.items()}


def mask_secret(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    tail = raw[-4:] if len(raw) >= 4 else raw
    return "••••••••" + tail


def _env_value(name: str, default: Any = "") -> Any:
    return getattr(settings, name, default)


def _env_provider_config(descriptor: ProviderDescriptor) -> tuple[bool, dict[str, Any], dict[str, str], bool]:
    public: dict[str, Any] = {}
    secret: dict[str, str] = {}
    enabled = False
    bot_enabled = False
    for logical, env_name in descriptor.env_fields.items():
        value = _env_value(env_name, "")
        if logical == "enabled":
            enabled = bool(value)
        elif logical == "bot_enabled":
            bot_enabled = bool(value)
        elif logical in descriptor.secret_fields:
            if str(value or "").strip():
                secret[logical] = str(value).strip()
        else:
            if str(value or "").strip():
                public[logical] = value
    return enabled, public, secret, bot_enabled


async def load_provider_config(db: AsyncSession, code: str) -> ProviderRuntimeConfig:
    descriptor = PROVIDER_DESCRIPTORS[str(code).strip().lower()]
    env_enabled, env_public, env_secret, env_bot_enabled = _env_provider_config(descriptor)
    row = (
        await db.execute(select(AdProviderConfig).where(AdProviderConfig.code == descriptor.code))
    ).scalar_one_or_none()

    if row is None:
        order = [x.strip() for x in str(settings.ADS_DEFAULT_PROVIDER_ORDER).split(",") if x.strip()]
        priority = order.index(descriptor.code) if descriptor.code in order else 1000
        return ProviderRuntimeConfig(
            descriptor=descriptor,
            enabled=env_enabled,
            priority=priority,
            miniapp_enabled=True,
            bot_enabled=env_bot_enabled,
            rewarded_enabled=True,
            public=env_public,
            secret=env_secret,
            countries_allow=(), countries_block=(), languages_allow=(), languages_block=(),
            verification_level=descriptor.verification_level,
            verification_mode=descriptor.verification_mode,
            health_status="unknown",
            moderation_status=None,
            last_success_at=None,
            last_error_at=None,
            last_error_code=None,
            source="env",
        )

    admin_public = dict(row.public_config_json or {})
    admin_config = dict(row.config_json or {})
    public = {**env_public, **{k: v for k, v in admin_public.items() if str(v or "").strip()}}
    public.update({k: v for k, v in admin_config.items() if k in descriptor.public_fields and str(v or "").strip()})
    secret = dict(env_secret)
    if row.secret_config_encrypted:
        secret.update(decrypt_secret_config(row.secret_config_encrypted))
    return ProviderRuntimeConfig(
        descriptor=descriptor,
        enabled=bool(row.enabled),
        priority=int(row.priority),
        miniapp_enabled=bool(row.miniapp_enabled),
        bot_enabled=bool(row.bot_enabled),
        rewarded_enabled=bool(row.rewarded_enabled),
        public=public,
        secret=secret,
        countries_allow=tuple(str(x).upper() for x in (row.countries_allow or []) if str(x).strip()),
        countries_block=tuple(str(x).upper() for x in (row.countries_block or []) if str(x).strip()),
        languages_allow=tuple(str(x) for x in (row.languages_allow or []) if str(x).strip()),
        languages_block=tuple(str(x) for x in (row.languages_block or []) if str(x).strip()),
        verification_level=str(row.verification_level or descriptor.verification_level),
        verification_mode=str(row.verification_mode or descriptor.verification_mode),
        health_status=str(row.health_status or "unknown"),
        moderation_status=(str(row.moderation_status) if row.moderation_status else None),
        last_success_at=row.last_success_at,
        last_error_at=row.last_error_at,
        last_error_code=(str(row.last_error_code) if row.last_error_code else None),
        source="admin_then_env",
    )


async def load_all_provider_configs(db: AsyncSession) -> list[ProviderRuntimeConfig]:
    configs = [await load_provider_config(db, code) for code in PROVIDER_DESCRIPTORS]
    return sorted(configs, key=lambda item: (item.priority, item.code))


def public_admin_view(config: ProviderRuntimeConfig) -> dict[str, Any]:
    secret_masks = {key: mask_secret(value) for key, value in config.secret.items() if value}
    return {
        "code": config.code,
        "title": config.descriptor.display_name,
        "enabled": config.enabled,
        "is_active": config.enabled,
        "priority": config.priority,
        "miniapp_enabled": config.miniapp_enabled,
        "bot_enabled": config.bot_enabled,
        "rewarded_enabled": config.rewarded_enabled,
        "is_configured": config.is_configured(),
        "configuration_status": "READY" if config.is_configured() else "NOT_CONFIGURED",
        "verification_level": config.verification_level,
        "verification_mode": config.verification_mode,
        "health": config.health_status,
        "moderation_status": config.moderation_status,
        "last_success_at": config.last_success_at.isoformat() if config.last_success_at else None,
        "last_error_at": config.last_error_at.isoformat() if config.last_error_at else None,
        "last_error_code": config.last_error_code,
        "public_config": config.public,
        "secret_masks": secret_masks,
        "countries_allow": list(config.countries_allow),
        "countries_block": list(config.countries_block),
        "languages_allow": list(config.languages_allow),
        "languages_block": list(config.languages_block),
        "capabilities": sorted(config.descriptor.capabilities),
        "config_schema": config.descriptor.schema(),
        "contract_status": config.descriptor.official_contract_status,
        "source": config.source,
        "note": config.descriptor.note,
    }
