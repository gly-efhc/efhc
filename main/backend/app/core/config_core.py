# backend/app/core/config_core.py
# ======================================================================
# Назначение кода:
# Центральные настройки проекта EFHC-Bot.
#
# Канон:
# • Все значения берутся из ENV (и могут быть заданы через .env файлы).
# • Настройки импортируются только через get_settings() (lru_cache).
# • В коде нет «зашитых» секретов (токен бота, DB URL и т.п.).
# ======================================================================

from __future__ import annotations

import hashlib
import os
from decimal import Decimal
from functools import lru_cache

from app.core.env_loader import load_env_files
from pydantic import (
    AliasChoices,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Загружаем .env файлы best-effort (ENV в окружении имеет приоритет).
load_env_files()

_LEGACY_CRON_DIGEST_SHA256 = (
    "a9599cb24e303890e7a46fabbe766f702ac648705d4708c7"
    "a571d34b9f8fddce"
)
_SECRET_PLACEHOLDERS = {
    "",
    "changeme",
    "change_me",
    "placeholder",
    "fill",
    "fill_me",
    "<fill_cron_secret>",
    "<your_cron_secret_min_32_chars>",
    "<your_hs256_secret_min_32_chars>",
}


def _secret_digest(value: object) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _is_placeholder_secret(value: object) -> bool:
    raw = str(value or "").strip()
    return raw.lower() in _SECRET_PLACEHOLDERS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            ".env",
            ".env.local",
            ".env.neon",
            ".env.prod",
            ".env.ci",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -----------------------------------------------------------------
    # Runtime
    # -----------------------------------------------------------------
    ENV: str = Field(default="local", description="local / prod / ci")
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Уровень логирования",
    )
    APP_VERSION: str = Field(
        default="0.0.0",
        description="Версия приложения",
    )
    APP_URL: str = Field(
        default="",
        description="Публичный origin Web App",
    )
    FRONTEND_URL: str = Field(
        default="",
        description="Публичный frontend origin",
    )
    BACKEND_URL: str = Field(
        default="",
        description="Публичный backend origin",
    )
    WEBHOOK_URL: str = Field(
        default="",
        description="Публичный Telegram webhook URL",
    )
    WEBAPP_URL: str = Field(
        default="",
        description="Публичный Telegram Web App URL",
    )
    WEB_PROFILE_PUBLIC_URL: str = Field(
        default="",
        description="Публичный профиль пользователя",
    )
    LOG_JSON: bool = Field(
        default=False,
        description="JSON логирование (prod)",
    )

    API_PREFIX: str = Field(
        default="/api",
        description="Префикс API роутов",
    )
    CORS_ORIGINS: list[str] = Field(
        default_factory=list,
        description="Разрешённые origins для CORS",
    )
    TRUSTED_HOSTS: list[str] = Field(
        default_factory=list,
        description="TrustedHostMiddleware allowlist",
    )
    OPENAPI_URL: str | None = Field(
        default="/openapi.json",
        description="URL OpenAPI схемы",
    )
    DOCS_URL: str | None = Field(
        default="/docs",
        description="URL Swagger UI",
    )
    REDOC_URL: str | None = Field(
        default="/redoc",
        description="URL ReDoc",
    )
    GZIP_MIN_BYTES: int = Field(
        default=500,
        ge=0,
        description="Минимальный размер для GZip",
    )
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=1_048_576,
        ge=1_024,
        le=10_485_760,
        description="Максимальный размер HTTP request body",
    )

    # Guard: "OPENAPI_URL", "DOCS_URL", "REDOC_URL"
    @field_validator(
        "OPENAPI_URL",
        "DOCS_URL",
        "REDOC_URL",
        mode="before",
    )
    @classmethod
    def _empty_public_docs_url_to_none(cls, v: object) -> str | None:
        """Convert null-like public docs ENV values to None.

        Prod templates use DOCS_URL=null / REDOC_URL=null /
        OPENAPI_URL=null. Pydantic receives ENV values as strings.
        This avoids registering literal ``/null`` or ``null`` paths.
        """
        if v is None:
            return None
        s = str(v).strip()
        if s.lower() in {"", "null", "none", "false", "off"}:
            return None
        return s

    DEBUG: bool = Field(
        default=False,
        description="Debug-режим backend",
    )
    ADS_TEST_MODE: bool = Field(
        default=False,
        description=(
            "Dev/test-only bypass for ad callback signatures"
        ),
    )
    ADS_ENABLED: bool = Field(
        default=True,
        description="Глобальный переключатель рекламного контура.",
    )
    ADS_CONFIG_SOURCE: str = Field(
        default="admin_then_env",
        description="Приоритет конфигурации ADS: Admin DB, затем ENV.",
    )
    ADS_DEFAULT_PROVIDER_ORDER: str = Field(
        default="monetag,adsgram,richads,tads,mybid,admaven,adexium",
        description="Глобальная fallback-очередь коммерческих провайдеров.",
    )
    ADS_SECRETS_ENCRYPTION_KEY: str = Field(
        default="",
        description="Fernet-ключ шифрования ADS credentials; хранится только в ENV.",
    )
    ADS_SESSION_TTL_SEC: int = Field(default=900, ge=60, le=86400)
    ADS_PROVIDER_TIMEOUT_SEC: int = Field(default=8, ge=1, le=120)
    ADS_MAX_FALLBACKS: int = Field(default=10, ge=0, le=50)
    ADS_AUTO_REVENUE_OPTIMIZER: bool = Field(default=False)
    ADS_TRUSTED_COUNTRY_HEADER: str = Field(default="")
    ADS_TRUSTED_CLIENT_IP_HEADER: str = Field(default="")
    ADS_BUILTIN_TIMER_ENABLED: bool = Field(default=False)
    ADS_BUILTIN_SECRET: str = Field(default="")
    ADS_BUILTIN_MIN_VIEW_SEC: int = Field(default=20, ge=1, le=3600)
    ADS_BUILTIN_TOKEN_TTL_SEC: int = Field(default=600, ge=30, le=86400)
    ADS_BUILTIN_MAX_DRIFT_SEC: int = Field(default=60, ge=0, le=3600)

    ADSGRAM_ENABLED: bool = Field(default=False)
    ADSGRAM_REWARD_BLOCK_ID: str = Field(default="")
    ADSGRAM_BOT_ENABLED: bool = Field(default=False)
    ADSGRAM_BOT_BLOCK_ID: str = Field(default="")
    ADSGRAM_BOT_TOKEN: str = Field(default="")
    ADSGRAM_REWARD_URL_ENABLED: bool = Field(default=False)

    MONETAG_ENABLED: bool = Field(default=False)
    MONETAG_REWARDED_ZONE_ID: str = Field(default="")
    MONETAG_POSTBACK_SECRET: str = Field(default="")
    MONETAG_SDK_SRC: str = Field(default="")

    RICHADS_ENABLED: bool = Field(default=False)
    RICHADS_SSP_ID: str = Field(default="")
    RICHADS_PUBLISHER_ID: str = Field(default="")
    RICHADS_WIDGET_ID: str = Field(default="")
    RICHADS_BID_FLOOR: str = Field(default="")

    TADS_ENABLED: bool = Field(default=False)
    TADS_WIDGET_ID: str = Field(default="")
    TADS_SDK_SRC: str = Field(default="")

    MYBID_ENABLED: bool = Field(default=False)
    MYBID_WIDGET_ID: str = Field(default="")
    MYBID_SDK_SRC: str = Field(default="")

    ADMAVEN_ENABLED: bool = Field(default=False)
    ADMAVEN_API_KEY: str = Field(default="")
    ADMAVEN_POSTBACK_SECRET: str = Field(default="")
    ADMAVEN_SCRIPT_SRC: str = Field(default="")

    ADEXIUM_ENABLED: bool = Field(default=False)
    ADEXIUM_WIDGET_ID: str = Field(default="")
    ADEXIUM_SDK_SRC: str = Field(
        default="https://cdn.adexium.tech/assets/js/adexium-widget.min.js"
    )
    AUTH_PROVIDER_FLAGS: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Runtime feature flags auth providers; отсутствие flag "
            "означает disabled"
        ),
    )
    AUTH_PROVIDER_TEST_FLAGS: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Отдельные test-only flags auth providers для ENV=ci"
        ),
    )
    TON_AUTH_CHALLENGE_RATE_WINDOW_SEC: int = Field(
        default=60,
        ge=1,
        le=3600,
        description=(
            "Окно rate-limit публичной выдачи TON auth challenge"
        ),
    )
    TON_AUTH_CHALLENGE_RATE_MAX_REQUESTS: int = Field(
        default=10,
        ge=1,
        le=1000,
        description=(
            "Максимум TON auth challenge на client fingerprint за окно"
        ),
    )
    TON_AUTH_CHALLENGE_MAX_OUTSTANDING: int = Field(
        default=5000,
        ge=1,
        le=1_000_000,
        description=(
            "Глобальный предел активных TON auth challenge"
        ),
    )
    TON_AUTH_CHALLENGE_CLEANUP_BATCH: int = Field(
        default=256,
        ge=1,
        le=10_000,
        description="Bounded cleanup terminal/expired auth challenge за выдачу",
    )
    DB_POOL_SIZE: int = Field(
        default=5,
        ge=1,
        description="Размер пула SQLAlchemy",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=10,
        ge=0,
        description="Максимальный overflow пула",
    )
    SCHEDULER_TICK_SECONDS: int = Field(
        default=600,
        ge=1,
        description="Интервал тика scheduler по умолчанию",
    )
    CHECK_TON_INBOX_INTERVAL_SEC: int = Field(
        default=600,
        ge=30,
        description="TON inbox scan interval in seconds",
    )
    CHECK_TON_INBOX_TIMEOUT_SEC: int = Field(
        default=900,
        ge=30,
        description="TON inbox task timeout in seconds",
    )
    TON_WATCHER_POLL_LIMIT: int = Field(
        default=200,
        ge=1,
        le=10_000,
        description="Maximum new TON transactions per scan",
    )
    TON_WATCHER_RETRY_LIMIT: int = Field(
        default=500,
        ge=1,
        le=50_000,
        description="Maximum TON reconciliation retry window",
    )
    TON_RECONCILE_EVERY_TICKS: int = Field(
        default=6,
        ge=1,
        le=10_000,
        description="Run full TON reconciliation every N scans",
    )
    TON_RECONCILE_HOURS: int = Field(
        default=24,
        ge=1,
        le=720,
        description="TON reconciliation lookback in hours",
    )

    @property
    def env_normalized(self) -> str:
        """SSOT нормализация переменной окружения ENV.

        Что делает:
        - Приводит ENV к каноническим значениям:
          local / dev / stage / prod / ci.

        Инвариант:
        - В проекте запрещено вычислять алиасы ENV «по месту».
          Любая логика опирается на это свойство.
        """
        v = (self.ENV or "local").strip().lower()
        aliases = {
            "production": "prod",
            "prod": "prod",
            "stage": "stage",
            "staging": "stage",
            "dev": "dev",
            "development": "dev",
            "local": "local",
            "ci": "ci",
            "test": "ci",
        }
        return aliases.get(v, v)

    @property
    def is_dev(self) -> bool:
        """Совместимый флаг dev/local/ci для логирования и scheduler."""
        return self.env_normalized in {"local", "dev", "ci"}

    def database_url_asyncpg(self) -> str:
        """Вернуть только канонический PostgreSQL asyncpg DSN.

        Разрешены только PostgreSQL-схемы. Любая иная схема считается
        конфигурационной ошибкой и должна падать на старте.
        """
        raw = str(getattr(self, "DATABASE_URL", "") or "").strip()
        if not raw:
            return raw
        if raw.startswith("postgresql+asyncpg://"):
            return raw
        if raw.startswith("postgresql://"):
            return raw.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            )
        if raw.startswith("postgres://"):
            return raw.replace(
                "postgres://",
                "postgresql+asyncpg://",
                1,
            )
        raise ValueError(
            "DATABASE_URL must use PostgreSQL only "
            "(postgresql+asyncpg://)"
        )

    # Serverless guard (Vercel)
    SERVERLESS: bool = Field(
        default=False,
        validation_alias=AliasChoices("SERVERLESS", "SCHED_SERVERLESS"),
        description=(
            "Если true — запрещаем вечные циклы (start()), "
            "используем /cron/tick"
        ),
    )

    # Секрет для защиты /cron/tick.
    # Local/dev/ci may keep it empty; prod/stage must provide a
    # high-entropy ENV value and must never use repository-known or
    # placeholder values.
    CRON_SECRET: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CRON_SECRET",
            "SCHED_CRON_SECRET",
        ),
        description=(
            "В prod/stage обязателен для X-Cron-Secret"
        ),
    )

    # -----------------------------------------------------------------
    # DB
    # -----------------------------------------------------------------
    DATABASE_URL: str = Field(
        default=(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/efhc"
        ),
        description="Async SQLAlchemy URL",
    )
    SYNC_DATABASE_URL: str = Field(
        default=(
            "postgresql://postgres:postgres@localhost:5432/efhc"
            "?sslmode=disable"
        ),
        description="Sync URL (alembic)",
    )
    DB_SCHEMA_CORE: str = Field(
        default="efhc_core",
        description="Главная схема данных",
    )

    DB_SCHEMA_ADMIN: str = Field(
        default="efhc_admin",
        description=(
            "Админская схема данных (таблицы "
            "админ-панели/банка/пакетов)"
        ),
    )

    @field_validator("DB_SCHEMA_CORE", mode="before")
    @classmethod
    def _canon_db__schema__core(cls, v: object) -> str:
        """Normalize schema aliases to canonical efhc_* names."""
        if v is None:
            return "efhc_core"
        s = str(v).strip()
        aliases = {
            "core": "efhc_core",
            "efhc": "efhc_core",
            "efhc-core": "efhc_core",
        }
        s = aliases.get(s, s)
        if s != "efhc_core":
            raise ValueError("DB_SCHEMA_CORE must be efhc_core")
        return s

    @field_validator("DB_SCHEMA_ADMIN", mode="before")
    @classmethod
    def _canon_db__schema__admin(cls, v: object) -> str:
        """Normalize schema aliases to canonical efhc_* names."""
        if v is None:
            return "efhc_admin"
        s = str(v).strip()
        aliases = {
            "admin": "efhc_admin",
            "efhc-admin": "efhc_admin",
        }
        s = aliases.get(s, s)
        if s != "efhc_admin":
            raise ValueError("DB_SCHEMA_ADMIN must be efhc_admin")
        return s

    # -----------------------------------------------------------------
    # Tasks (defaults)
    # -----------------------------------------------------------------
    TASK_REWARD_BONUS_EFHC_DEFAULT: Decimal = Field(
        default=Decimal("0"),
        description=(
            "Дефолтный бонус (bonus EFHC) для "
            "task, если не задано явно."
        ),
    )
    # -----------------------------------------------------------------
    # Telegram Bot
    # -----------------------------------------------------------------
    BOT_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TELEGRAM_BOT_TOKEN",
            "BOT_TOKEN",
        ),
        description="Telegram Bot Token",
    )
    ADMIN_TG_ID: int = Field(
        default=0,
        validation_alias=AliasChoices("ADMIN_TG_ID", "ADMIN_ID"),
        description="Единственный главный админ TG ID",
    )

    ADMIN_TG_IDS: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "ADMIN_TG_IDS",
        ),
        description=(
            "Whitelist админов (TG IDs). Если задан — используется "
            "вместо ADMIN_TG_ID"
        ),
    )

    ADMIN_NOTIFICATIONS_CHAT_ID: str = Field(
        default="",
        validation_alias=AliasChoices(
            "ADMIN_NOTIFICATIONS_CHAT_ID",
        ),
        description="Один chat id для служебных уведомлений",
    )

    ADMIN_NOTIFICATIONS_CHAT_IDS: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "ADMIN_NOTIFICATIONS_CHAT_IDS",
        ),
        description=(
            "Список chat id или @channel для watcher/service alerts"
        ),
    )

    # -----------------------------------------------------------------
    # Webhook
    # -----------------------------------------------------------------
    TELEGRAM_WEBHOOK_PATH: str = Field(
        default="/api/tg/webhook",
        description="Канонический production webhook path",
    )
    TELEGRAM_WEBHOOK_URL: str = Field(
        default="",
        description="Полный URL webhook (опционально)",
    )

    TELEGRAM_WEBHOOK_SECRET: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TELEGRAM_WEBHOOK_SECRET",
            "WEBHOOK_SECRET",
        ),
        description="Secret token for Telegram webhook",
    )

    SECRET_KEY: str = Field(
        default="",
        description="HS256 secret for signed server tokens",
    )

    @field_validator("TELEGRAM_WEBHOOK_PATH", mode="before")
    @classmethod
    def _canonical_webhook_path(cls, value: object) -> str:
        path = str(value or "").strip()
        if path != "/api/tg/webhook":
            raise ValueError(
                "TELEGRAM_WEBHOOK_PATH must be /api/tg/webhook"
            )
        return path

    @field_validator("TON_API_BASE_URL", mode="before")
    @classmethod
    def _canonical_ton_api_base(cls, value: object) -> str:
        raw = str(value or "https://tonapi.io").strip().rstrip("/")
        if raw.endswith("/v2"):
            raw = raw[:-3].rstrip("/")
        if not raw.startswith("https://"):
            raise ValueError("TON_API_BASE_URL must use HTTPS")
        return raw

    @field_validator("TON_NETWORK", mode="before")
    @classmethod
    def _canonical_ton_network(cls, value: object) -> str:
        network = str(value or "mainnet").strip().lower()
        if network not in {"mainnet", "testnet"}:
            raise ValueError("TON_NETWORK must be mainnet or testnet")
        return network

    @model_validator(mode="after")
    def _validate_auth_provider_feature_flags(self) -> Settings:
        """Проверить fail-closed provider flags при startup."""

        from app.identity.provider_registry import (
            AuthProviderFeatureFlags,
        )

        AuthProviderFeatureFlags.from_mappings(
            environment=self.env_normalized,
            runtime_flags=self.AUTH_PROVIDER_FLAGS,
            test_flags=self.AUTH_PROVIDER_TEST_FLAGS,
        )
        return self

    @model_validator(mode="after")
    def _canonical_runtime_contract(self) -> Settings:
        if not self.PAYMENTS_RECEIVER_ADDRESS:
            self.PAYMENTS_RECEIVER_ADDRESS = self.TON_MAIN_WALLET
        if not self.TON_WALLET_ADDRESS:
            self.TON_WALLET_ADDRESS = self.TON_MAIN_WALLET
        if self.env_normalized == "prod":
            required = {
                "TON_API_KEY": self.TON_API_KEY,
                "TON_MAIN_WALLET": self.TON_MAIN_WALLET,
                "TON_NFT_COLLECTION": self.TON_NFT_COLLECTION,
                "TON_WALLET_ADDRESS": self.TON_WALLET_ADDRESS,
            }
            missing = [
                name
                for name, value in required.items()
                if not str(value or "").strip()
            ]
            if missing:
                raise ValueError(
                    "Missing production TON settings: "
                    + ", ".join(missing)
                )
        return self

    @model_validator(mode="after")
    def _require_secrets_in_prod(self) -> Settings:
        """Fail-closed проверка секретов защищённых окружений.

        В local/dev/ci control-plane secrets могут отсутствовать.
        Production и stage обязаны отвергать конфигурацию без секретов
        Telegram webhook, HS256 и cron.
        """
        env = self.env_normalized
        if env in {"prod", "stage"} and not str(
            self.TELEGRAM_WEBHOOK_SECRET or ""
        ).strip():
            raise ValueError(
                "TELEGRAM_WEBHOOK_SECRET обязателен в production/stage."
            )
        if env in {"prod", "stage"}:
            secret_key = str(self.SECRET_KEY or "").strip()
            if _is_placeholder_secret(secret_key) or len(secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY должен содержать не менее 32 символов "
                    "и не быть placeholder в production/stage."
                )
            if bool(self.ADS_TEST_MODE):
                raise ValueError(
                    "ADS_TEST_MODE must be false in production/stage."
                )
            cron_secret = str(self.CRON_SECRET or "").strip()
            if (
                _is_placeholder_secret(cron_secret)
                or len(cron_secret) < 32
                or _secret_digest(cron_secret)
                == _LEGACY_CRON_DIGEST_SHA256
            ):
                raise ValueError(
                    "CRON_SECRET must be high-entropy and set "
                    "from ENV in production/stage."
                )
        return self

    HUB_EFHC_BUY_URL: str = Field(
        default="",
        description="External EFHC buy-flow URL for Hub handoff",
    )

    HUB_EFHC_HANDOFF_TTL_SEC: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="TTL for signed Hub EFHC handoff token",
    )

    # -----------------------------------------------------------------
    # I18N (16 серверных локализаций; frontend runtime: 16 языков)
    # -----------------------------------------------------------------
    SUPPORTED_LANGS: list[str] = Field(
        # Канон: все 16 runtime-языков, включая pt, ko и ja.
        default_factory=lambda: [
            "en",
            "ru",
            "uk",
            "de",
            "es",
            "fr",
            "it",
            "pl",
            "tr",
            "da",
            "id",
            "hi",
            "sw",
            "pt",
            "ko",
            "ja",
        ],
        description="Коды поддерживаемых языков",
    )

    # -----------------------------------------------------------------
    # VIP NFT / TON
    # -----------------------------------------------------------------
    TON_NETWORK: str = Field(
        default="mainnet",
        description="TON network: mainnet or testnet",
    )
    TON_API_BASE_URL: str = Field(
        default="https://tonapi.io",
        description="TonAPI origin without /v2 suffix",
    )
    TON_API_KEY: str = Field(
        default="",
        description="TonAPI key",
    )
    TON_MAIN_WALLET: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TON_MAIN_WALLET",
            "TON_WALLET",
            "PROJECT_TON_WALLET",
        ),
        description="Main TON wallet for deposits and settlement",
    )
    TON_NFT_COLLECTION: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TON_NFT_COLLECTION",
            "VIP_NFT_COLLECTION",
        ),
        description="VIP NFT collection address",
    )
    TON_ADMIN_NFT_IDS: list[str] = Field(
        default_factory=list,
        description=(
            "Точные адреса NFT-item специальных Admin NFT внутри "
            "TON_NFT_COLLECTION. Пустой список отключает NFT-доступ."
        ),
    )
    TON_WALLET_ADDRESS: str = Field(
        default="",
        description="TON wallet used by shop/admin payment routes",
    )

    # -----------------------------------------------------------------
    # Energy generation SSOT constants (string -> Decimal d8)
    # -----------------------------------------------------------------
    GEN_PER_SEC_BASE_KWH: str = Field(
        default="0.00000692",
        description="SSOT base generation rate (kWh/sec) as string",
    )
    GEN_PER_SEC_VIP_KWH: str = Field(
        default="0.00000741",
        description="SSOT VIP generation rate (kWh/sec) as string",
    )
    EFHC_KWH_RATE: str = Field(
        default="1.0",
        description="SSOT conversion rate EFHC:kWh as string",
    )

    # -----------------------------------------------------------------
    # Payments (A+B intents) — TonConnect
    # -----------------------------------------------------------------
    PAYMENTS_RECEIVER_ADDRESS: str = Field(
        default="",
        description=(
            "Compatibility receiver override; TON_MAIN_WALLET is "
            "the canonical production value."
        ),
    )
    EFHC_JETTON_MASTER_ADDRESS: str = Field(
        default="EQDNcpWf9mXgSPDubDCzvuaX-juL4p8MuUwrQC-36sARRBuw",
        description="EFHC jetton master address (mainnet, canon)",
    )

    EFHC_JETTON_DECIMALS: int = Field(
        default=8,
        ge=0,
        le=255,
        description="EFHC jetton decimals (canon, d8)",
    )

    USDT_JETTON_MASTER_ADDRESS: str = Field(
        default="",
        description=(
            "TON USDT jetton master address (for jetton transfer)"
        ),
    )
    JETTON_TRANSFER_FEE_NANO: str = Field(
        default="50000000",
        description="TON fee (nanotons) for jetton transfer message",
    )
    JETTON_FORWARD_TON_AMOUNT_NANO: str = Field(
        default="1",
        description=(
            "Forward TON amount for TEP-74 transfer notification"
        ),
    )
    VIP_NFT_NETWORK: str = Field(
        default="mainnet",
        description="mainnet/testnet",
    )



@lru_cache(maxsize=1)
def _get_settings_cached() -> Settings:
    return Settings()


def get_settings() -> Settings:
    """SSOT: получить настройки проекта.

    В CI/тестах Settings часто собирается на лету через monkeypatch/env.
    Кэширование в таких средах ломает детерминизм.
    """
    raw = (os.getenv("ENV") or "local").strip().lower()
    aliases = {
        "production": "prod",
        "prod": "prod",
        "stage": "stage",
        "staging": "stage",
        "dev": "dev",
        "development": "dev",
        "local": "local",
        "ci": "ci",
        "test": "ci",
    }
    env_norm = aliases.get(raw, raw)

    if env_norm == "ci" or os.getenv("PYTEST_CURRENT_TEST"):
        return Settings()

    return _get_settings_cached()


# Совместимость: в проекте и тестах исторически вызывали
# get_settings.cache_clear().
# Мы сохраняем этот API, но кэш находится во внутренней функции
# _get_settings_cached.
get_settings.__dict__["cache_clear"] = _get_settings_cached.cache_clear
get_settings.__dict__["cache_info"] = _get_settings_cached.cache_info

settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
