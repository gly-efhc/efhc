# backend/app/services/nft_check_service.py
# ======================================================================
# Проверка VIP по наличию NFT из канонической TON-коллекции в кошельке
# пользователя. Современный источник кошелька: wallet_bindings;
# users.ton_wallet больше не является источником ownership.
# Денежные операции не выполняются.
#
# Канон:
# - VIP = факт наличия NFT из TON_NFT_COLLECTION.
# - Авто-минтинг запрещён. Shop/покупка — отдельный процесс.
#
# Таблицы кэша/логов опциональны. Если их нет — сервис работает без них.
# ======================================================================

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.database_core import get_session_factory
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_admin_table, canon_schema
from app.integrations.ton_api_urls import ton_api_v2
from app.lib.time import utcnow
from app.services.energy_service import (
    set_user_vip_with_energy_checkpoint,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
S = get_settings()


# ======================================================================
# Конфигурация (.env)
# ======================================================================

SCHEMA_CORE: str = canon_schema(
    getattr(S, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core",
)
SCHEMA_ADMIN: str = (
    getattr(S, "DB_SCHEMA_ADMIN", SCHEMA_CORE) or SCHEMA_CORE
)

TON_API_BASE: str = ton_api_v2(S.TON_API_BASE_URL)
TON_API_KEY: str = str(getattr(S, "TON_API_KEY", "") or "")

TON_NFT_COLLECTION: str = str(
    getattr(
        S,
        "TON_NFT_COLLECTION",
        getattr(S, "GETGEMS_COLLECTION", ""),
    )
    or ""
)
TON_ADMIN_NFT_IDS: tuple[str, ...] = tuple(
    str(value).strip()
    for value in (getattr(S, "TON_ADMIN_NFT_IDS", []) or [])
    if str(value).strip()
)

# TTL кэша (сек)
NFT_CACHE_TTL_SECONDS: int = int(
    getattr(S, "NFT_CACHE_TTL_SECONDS", 900) or 900
)

# Размер батча
VIP_CHECK_BATCH_SIZE: int = int(
    getattr(S, "NFT_CHECK_BATCH_SIZE", 500) or 500
)


# ======================================================================
# DTO
# ======================================================================


class NftAsset(BaseModel):
    """Упрощённое описание NFT из коллекции TON."""

    collection_address: str
    token_id: str
    item_address: str | None = None
    name: str | None = None
    verified: bool = False
    raw: dict[str, Any] | None = None


class NftWalletCheck(BaseModel):
    """Результат проверки одного active verified TON-кошелька."""

    ton_wallet: str
    vip_assets: list[NftAsset] = Field(default_factory=list)
    admin_assets: list[NftAsset] = Field(default_factory=list)
    all_assets: list[NftAsset] = Field(default_factory=list)
    source: str = Field(default="LIVE", description="LIVE | CACHE")


class NftCheckResult(BaseModel):
    """Агрегированный результат VIP/Admin NFT для одного global_id."""

    global_id: int
    ton_wallet: str
    is_vip: bool
    has_admin_nft: bool = False
    vip_assets: list[NftAsset] = Field(default_factory=list)
    admin_assets: list[NftAsset] = Field(default_factory=list)
    all_assets: list[NftAsset] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utcnow)
    source: str = Field(default="LIVE", description="LIVE | CACHE")
    wallet_checks: list[NftWalletCheck] = Field(
        default_factory=list,
        exclude=True,
    )


class NftCheckError(RuntimeError):
    """Ошибка сервиса проверки NFT/VIP."""


@dataclass
class VipBatchStats:
    total: int
    changed: int


@dataclass(frozen=True)
class NftWalletCandidate:
    """Кандидат VIP/NFT batch sync из canonical wallet_bindings."""

    global_id: int
    wallet_address: str
    wallet_source: str


# ======================================================================
# HTTP helper (динамический импорт httpx)
# ======================================================================


async def _http_get_json(
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GET → JSON. Если httpx отсутствует — поднимаем NftCheckError."""
    try:
        import httpx  # type: ignore
    except Exception as exc:  # noqa: BLE001
        msg = (
            "Зависимость httpx не установлена. Добавьте "
            "'httpx[http2]' в зависимости."
        )
        raise NftCheckError(msg) from exc

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            http2=True,
        ) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        raise NftCheckError(f"Ошибка TON API: {exc}") from exc


# ======================================================================
# Кэш efhc_admin.nft_check_cache_ton (опционально)
# ======================================================================


class _Cache:
    @staticmethod
    async def _table_exists(db: AsyncSession) -> bool:
        """True, если таблица кэша существует."""
        sql = text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :table
            LIMIT 1
            """
        )
        r: Result = await db.execute(
            sql,
            {
                "schema": SCHEMA_ADMIN,
                "table": "nft_check_cache_ton",
            },
        )
        return r.fetchone() is not None

    @staticmethod
    async def try_read(
        db: AsyncSession,
        address: str,
    ) -> list[dict[str, Any]] | None:
        """Вернуть кэш, если он не просрочен; иначе None."""
        if not await _Cache._table_exists(db):
            return None

        min_ts = utcnow() - timedelta(
            seconds=NFT_CACHE_TTL_SECONDS,
        )
        sql = text(
            """
            SELECT assets_json 
            FROM efhc_admin.nft_check_cache_ton
            WHERE address = :addr
              AND snapshot_at >= :min_ts
            LIMIT 1
            """
        )
        r: Result = await db.execute(
            sql,
            {
                "addr": address,
                "min_ts": min_ts,
            },
        )
        row = r.fetchone()
        if not row:
            return None
        assets = row.assets_json  # type: ignore[attr-defined]
        return assets  # type: ignore[no-any-return]

    @staticmethod
    async def write(
        db: AsyncSession,
        address: str,
        assets_json: list[dict[str, Any]],
    ) -> None:
        """Записать/обновить кэш. Если таблицы нет — пропустить."""
        if not await _Cache._table_exists(db):
            return

        sql = text(
            """
            INSERT INTO efhc_admin.nft_check_cache_ton (
                address, 
                assets_json,
                snapshot_at
            )
            VALUES (
                :addr,
                CAST(:assets AS jsonb),
                NOW() AT TIME ZONE 'UTC'
            )
            ON CONFLICT (address) DO UPDATE
            SET assets_json = EXCLUDED.assets_json,
                snapshot_at = EXCLUDED.snapshot_at
            """
        )
        await db.execute(
            sql,
            {
                "addr": address,
                "assets": _json_dumps(assets_json),
            },
        )


# ======================================================================
# Основной сервис проверки NFT/VIP
# ======================================================================


class NftCheckService:
    """VIP проверки и массовая синхронизация users.is_vip."""

    @staticmethod
    async def get_wallets_for_user(
        db: AsyncSession,
        global_id: int,
    ) -> list[str]:
        """Разрешить active verified TON wallet bindings пользователя."""

        binding_result: Result = await db.execute(
            text(
                """
                SELECT wallet_address
                  FROM efhc_core.wallet_bindings
                 WHERE global_id = :global_id
                   AND is_active = TRUE
                   AND proof_verified = TRUE
                   AND wallet_address IS NOT NULL
                   AND LENGTH(TRIM(wallet_address)) > 0
                 ORDER BY
                    is_primary DESC,
                    proof_verified_at DESC NULLS LAST,
                    updated_at DESC NULLS LAST,
                    id DESC
                """
            ),
            {"global_id": int(global_id)},
        )
        wallets: list[str] = []
        seen: set[str] = set()
        for row in binding_result.fetchall():
            wallet = str(getattr(row, "wallet_address", "") or "").strip()
            if wallet and wallet not in seen:
                wallets.append(wallet)
                seen.add(wallet)
        return wallets

    @staticmethod
    async def get_wallet_for_user(
        db: AsyncSession,
        global_id: int,
    ) -> str | None:
        """Совместимый resolver: вернуть первый канонический wallet source."""

        wallets = await NftCheckService.get_wallets_for_user(db, global_id)
        return wallets[0] if wallets else None

    @staticmethod
    async def get_wallet_for_global_id(
        db: AsyncSession,
        global_id: int,
    ) -> str | None:
        """Совместимый фасад канонического wallet resolver для ``global_id``."""

        gid = int(global_id)
        if gid < 1 or gid > 9_999_999_999:
            return None
        return await NftCheckService.get_wallet_for_user(db, gid)

    @staticmethod
    async def check_user_vip(
        db: AsyncSession,
        global_id: int,
        force_refresh: bool = False,
    ) -> NftCheckResult | None:
        """Проверить все active verified TON wallets; БД не изменяет."""

        wallets = await NftCheckService.get_wallets_for_user(db, global_id)
        if not wallets:
            return None

        wallet_checks: list[NftWalletCheck] = []
        aggregate_all: list[NftAsset] = []
        aggregate_vip: list[NftAsset] = []
        aggregate_admin: list[NftAsset] = []

        for wallet in wallets:
            source = "LIVE"
            all_assets: list[NftAsset]
            if not force_refresh:
                cached = await _Cache.try_read(db, wallet)
                if cached is not None:
                    try:
                        if any(
                            not isinstance(asset, dict)
                            or "verified" not in asset
                            for asset in cached
                        ):
                            raise ValueError(
                                "legacy cache не содержит NFT verification state"
                            )
                        all_assets = [NftAsset(**asset) for asset in cached]
                        source = "CACHE"
                    except Exception:  # noqa: BLE001
                        all_assets = await _fetch_ton_assets(wallet)
                        await _Cache.write(
                            db,
                            wallet,
                            [asset.model_dump() for asset in all_assets],
                        )
                else:
                    all_assets = await _fetch_ton_assets(wallet)
                    await _Cache.write(
                        db,
                        wallet,
                        [asset.model_dump() for asset in all_assets],
                    )
            else:
                all_assets = await _fetch_ton_assets(wallet)
                await _Cache.write(
                    db,
                    wallet,
                    [asset.model_dump() for asset in all_assets],
                )

            vip_assets = _filter_vip_assets(
                all_assets,
                TON_NFT_COLLECTION,
            )
            admin_assets = _filter_admin_nft_assets(all_assets)
            wallet_checks.append(
                NftWalletCheck(
                    ton_wallet=wallet,
                    vip_assets=vip_assets,
                    admin_assets=admin_assets,
                    all_assets=all_assets,
                    source=source,
                )
            )
            aggregate_all.extend(all_assets)
            aggregate_vip.extend(vip_assets)
            aggregate_admin.extend(admin_assets)

        aggregate_source = (
            "CACHE"
            if wallet_checks
            and all(check.source == "CACHE" for check in wallet_checks)
            else "LIVE"
        )
        return NftCheckResult(
            global_id=global_id,
            ton_wallet=wallets[0],
            is_vip=bool(aggregate_vip),
            has_admin_nft=bool(aggregate_admin),
            vip_assets=aggregate_vip,
            admin_assets=aggregate_admin,
            all_assets=aggregate_all,
            checked_at=utcnow(),
            source=aggregate_source,
            wallet_checks=wallet_checks,
        )

    @staticmethod
    async def sync_users_is_vip(
        db: AsyncSession,
        global_ids: Sequence[int],
        force_refresh: bool = False,
        log_table: str = "vip_status_log",
    ) -> dict[int, bool]:
        """Массово синхронизировать users.is_vip по списку global_id."""
        out: dict[int, bool] = {}
        for global_id in global_ids:
            try:
                res = await NftCheckService.check_user_vip(
                    db,
                    global_id,
                    force_refresh=force_refresh,
                )
                if res is None:
                    before = await _read_users_is_vip(db, global_id)
                    updated = await _write_users_is_vip(
                        db,
                        global_id,
                        False,
                    )
                    out[global_id] = False
                    changed = (
                        updated
                        and before is not None
                        and before is not False
                    )
                    if changed:
                        await _try_write_vip_log(
                            db,
                            global_id,
                            old=before,
                            new=False,
                            table=log_table,
                        )
                    continue

                for wallet_check in res.wallet_checks:
                    await _sync_admin_nft_wallet_state(
                        db,
                        ton_wallet_id=wallet_check.ton_wallet,
                        admin_assets=wallet_check.admin_assets,
                    )
                before = await _read_users_is_vip(db, global_id)
                updated = await _write_users_is_vip(
                    db,
                    global_id,
                    res.is_vip,
                )
                out[global_id] = res.is_vip
                changed = (
                    updated
                    and before is not None
                    and before != res.is_vip
                )
                if changed:
                    await _try_write_vip_log(
                        db,
                        global_id,
                        old=before,
                        new=res.is_vip,
                        table=log_table,
                    )
            except NftCheckError as exc:
                logger.warning(
                    "VIP check failed for global_id=%s: %s",
                    global_id,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "VIP check unexpected error for global_id=%s: %s",
                    global_id,
                    exc,
                )
        return out


# ======================================================================
# Вспомогательные функции (SQL/TON API)
# ======================================================================


async def _fetch_ton_assets(address: str) -> list[NftAsset]:
    """Забрать NFT-активы для TON-адреса и нормализовать."""
    if not TON_NFT_COLLECTION:
        logger.warning(
            "TON_NFT_COLLECTION не задан — VIP будет всегда False."
        )

    base = TON_API_BASE.rstrip("/")
    url = f"{base}/accounts/{address}/nfts"

    headers: dict[str, str] = {}
    if TON_API_KEY:
        headers["Authorization"] = f"Bearer {TON_API_KEY}"

    params: dict[str, Any] = {"limit": 1000}
    data = await _http_get_json(url, headers=headers, params=params)

    items = data.get("nft_items") or data.get("nfts") or []
    out: list[NftAsset] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        collection_obj = item.get("collection") or {}
        collection_addr = ""
        if isinstance(collection_obj, dict):
            collection_addr = str(collection_obj.get("address") or "")
        if not collection_addr:
            collection_addr = str(item.get("collection_address") or "")

        item_address = str(item.get("address") or "").strip() or None
        token_id = str(
            item.get("index")
            or item.get("token_id")
            or item.get("id")
            or item_address
            or ""
        )

        md = item.get("metadata")
        name = md.get("name") if isinstance(md, dict) else None
        if not isinstance(name, str):
            name = None

        if not collection_addr or not token_id:
            continue

        out.append(
            NftAsset(
                collection_address=collection_addr,
                token_id=token_id,
                item_address=item_address,
                name=name,
                verified=item.get("verified") is True,
                raw=item,
            )
        )

    return out


def _filter_vip_assets(
    assets: list[NftAsset],
    vip_collection: str,
) -> list[NftAsset]:
    """Фильтр по адресу целевой коллекции."""
    if not vip_collection:
        return []
    return [
        asset
        for asset in assets
        if asset.verified is True
        and asset.collection_address == vip_collection
    ]


def _admin_nft_id_for_asset(asset: NftAsset) -> str | None:
    """Вернуть точный NFT-item address, разрешённый через ENV."""
    configured = set(TON_ADMIN_NFT_IDS)
    if not configured:
        return None
    item_address = str(asset.item_address or "").strip()
    if item_address and item_address in configured:
        return item_address
    return None


def _filter_admin_nft_assets(
    assets: list[NftAsset],
) -> list[NftAsset]:
    """Найти специальные Admin NFT только внутри VIP-коллекции."""
    vip_assets = _filter_vip_assets(assets, TON_NFT_COLLECTION)
    return [
        asset
        for asset in vip_assets
        if _admin_nft_id_for_asset(asset) is not None
    ]


async def _sync_admin_nft_wallet_state(
    db: AsyncSession,
    *,
    ton_wallet_id: str,
    admin_assets: list[NftAsset],
) -> None:
    """Синхронизировать вычисленный Admin NFT-доступ для кошелька.

    ENV-список точных NFT-item address из TON_ADMIN_NFT_IDS является
    источником полномочия. Таблица
    ``admin_nft_whitelist`` хранит только материализованный результат
    последней штатной NFT-проверки и не используется для ручной выдачи
    права доступа. Ошибка этого вспомогательного кэша не должна ломать VIP.
    """

    wallet = str(ton_wallet_id or "").strip()
    if not wallet:
        return

    matched_nft_id: str | None = None
    if admin_assets:
        matched_nft_id = _admin_nft_id_for_asset(admin_assets[0])

    try:
        async with db.begin_nested():
            if matched_nft_id is None:
                await db.execute(
                    text(
                        """
                        UPDATE efhc_admin.admin_nft_whitelist
                           SET is_active = FALSE,
                               revoked_at = COALESCE(revoked_at, NOW()),
                               updated_at = NOW()
                         WHERE ton_wallet_id = :ton_wallet_id
                           AND source = 'env_nft'
                        """
                    ),
                    {"ton_wallet_id": wallet},
                )
                return

            await db.execute(
                text(
                    """
                    UPDATE efhc_admin.admin_nft_whitelist
                       SET is_active = FALSE,
                           revoked_at = COALESCE(revoked_at, NOW()),
                           updated_at = NOW()
                     WHERE nft_id = :nft_id
                       AND ton_wallet_id <> :ton_wallet_id
                       AND source = 'env_nft'
                       AND is_active = TRUE
                    """
                ),
                {
                    "ton_wallet_id": wallet,
                    "nft_id": matched_nft_id,
                },
            )

            await db.execute(
                text(
                    """
                    INSERT INTO efhc_admin.admin_nft_whitelist (
                        ton_wallet_id, nft_id, role, source, is_active,
                        note, created_at, updated_at, revoked_at
                    ) VALUES (
                        :ton_wallet_id, :nft_id, 'admin', 'env_nft', TRUE,
                        'обнаружено NFT-проверкой', NOW(), NOW(), NULL
                    )
                    ON CONFLICT (ton_wallet_id) DO UPDATE SET
                        nft_id = EXCLUDED.nft_id,
                        role = EXCLUDED.role,
                        source = EXCLUDED.source,
                        is_active = TRUE,
                        note = EXCLUDED.note,
                        updated_at = NOW(),
                        revoked_at = NULL
                    """
                ),
                {
                    "ton_wallet_id": wallet,
                    "nft_id": matched_nft_id,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Admin NFT materialization failed for wallet=%s: %s",
            wallet,
            exc,
        )


def _json_dumps(obj: Any) -> str:
    """Безопасный json.dumps для записи в БД."""
    try:
        import json

        return json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except Exception:  # noqa: BLE001
        return str(obj)


async def _read_users_is_vip(
    db: AsyncSession,
    global_id: int,
) -> bool | None:
    """Прочитать users.is_vip для global_id."""
    sql = text(
        """
        SELECT is_vip
        FROM efhc_core.users
        WHERE global_id = :global_id
        LIMIT 1 
        """
    )
    r: Result = await db.execute(sql, {"global_id": global_id})
    row = r.fetchone()
    if not row or getattr(row, "is_vip", None) is None:
        return None
    return bool(row.is_vip)  # type: ignore[attr-defined]


async def _write_users_is_vip(
    db: AsyncSession,
    global_id: int,
    flag: bool,
) -> bool:
    """Сменить VIP только через точный BASE/VIP energy checkpoint."""

    return cast(
        bool,
        await set_user_vip_with_energy_checkpoint(
            db,
            global_id=int(global_id),
            new_is_vip=bool(flag),
        ),
    )


async def _try_write_vip_log(
    db: AsyncSession,
    global_id: int,
    old: bool | None,
    new: bool,
    table: str = "vip_status_log",
) -> None:
    """Записать лог изменения VIP, если таблица существует."""
    table = canon_admin_table(table)
    exists_sql = text(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema
          AND table_name = :table
        LIMIT 1
        """
    )
    r: Result = await db.execute(
        exists_sql,
        {"schema": SCHEMA_ADMIN, "table": table},
    )
    if r.fetchone() is None:
        return

    insert_sql = text(
        """
        INSERT INTO efhc_admin.{table} (
            global_id,
            old_flag,
            new_flag,
            created_at
        ) 
        VALUES (
            :global_id,
            :old,
            :new,
            NOW() AT TIME ZONE 'UTC'
        )
        """
    )
    await db.execute(
        insert_sql,
        {"global_id": global_id, "old": old, "new": new},
    )


async def _clear_stale_vip_without_wallet_sources(
    db: AsyncSession,
) -> list[int]:
    """Снять stale VIP через тот же checkpoint boundary для каждого owner."""

    result: Result = await db.execute(
        text(
            """
            SELECT u.global_id
              FROM efhc_core.users AS u
             WHERE u.is_vip = TRUE
               AND NOT EXISTS (
                   SELECT 1
                     FROM efhc_core.wallet_bindings wb
                    WHERE wb.global_id = u.global_id
                      AND wb.is_active = TRUE
                      AND wb.proof_verified = TRUE
                      AND wb.wallet_address IS NOT NULL
                      AND LENGTH(TRIM(wb.wallet_address)) > 0
               )
             ORDER BY u.global_id ASC
            """
        )
    )
    global_ids = [int(row.global_id) for row in result.fetchall()]
    updated: list[int] = []
    for global_id in global_ids:
        if await _write_users_is_vip(db, global_id, False):
            updated.append(global_id)
    return updated


# ======================================================================
# High-level сценарии
# ======================================================================


async def _fetch_wallet_candidates_batch(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
) -> list[NftWalletCandidate]:
    """Вернуть canonical active verified wallet candidates без дублей."""
    sql = text(
        """
        SELECT DISTINCT ON (wb.global_id)
            wb.global_id,
            wb.wallet_address AS wallet_address,
            'wallet_bindings' AS wallet_source
        FROM efhc_core.wallet_bindings wb
        WHERE wb.is_active = TRUE
          AND wb.proof_verified = TRUE
          AND wb.wallet_address IS NOT NULL
          AND LENGTH(TRIM(wb.wallet_address)) > 0
        ORDER BY
            wb.global_id ASC,
            wb.is_primary DESC,
            wb.proof_verified_at DESC NULLS LAST,
            wb.updated_at DESC NULLS LAST,
            wb.id DESC
        OFFSET :off
        LIMIT :lim
        """
    )
    r: Result = await db.execute(
        sql,
        {"off": int(offset), "lim": int(limit)},
    )
    candidates: list[NftWalletCandidate] = []
    for row in r.fetchall():
        wallet = str(row.wallet_address).strip()
        if not wallet:
            continue
        candidates.append(
            NftWalletCandidate(
                global_id=int(row.global_id),
                wallet_address=wallet,
                wallet_source=str(row.wallet_source),
            )
        )
    return candidates


async def _fetch_global_ids_with_wallet_batch(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
) -> list[int]:
    """Получить batch global_id через canonical wallet resolver."""
    candidates = await _fetch_wallet_candidates_batch(
        db,
        offset=offset,
        limit=limit,
    )
    return [c.global_id for c in candidates]


async def check_user_vip_once(
    db: AsyncSession,
    *,
    global_id: int,
    force_refresh: bool = False,
) -> NftCheckResult | None:
    """Проверить и синхронизировать одного пользователя."""
    try:
        res = await NftCheckService.check_user_vip(
            db,
            global_id,
            force_refresh=force_refresh,
        )
    except NftCheckError as exc:
        logger.warning(
            "check_user_vip_once: external error for global_id=%s: %s",
            global_id,
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            (
                "check_user_vip_once: unexpected error "
                "for global_id=%s: %s"
            ),
            global_id,
            exc,
        )
        return None

    if res is None:
        before = await _read_users_is_vip(db, global_id)
        updated = await _write_users_is_vip(db, global_id, False)
        if updated and before is not None and before is not False:
            await _try_write_vip_log(
                db,
                global_id,
                old=before,
                new=False,
            )
        return None

    for wallet_check in res.wallet_checks:
        await _sync_admin_nft_wallet_state(
            db,
            ton_wallet_id=wallet_check.ton_wallet,
            admin_assets=wallet_check.admin_assets,
        )
    before = await _read_users_is_vip(db, global_id)
    updated = await _write_users_is_vip(db, global_id, res.is_vip)
    if updated and before is not None and before != res.is_vip:
        await _try_write_vip_log(
            db,
            global_id,
            old=before,
            new=res.is_vip,
        )
    return res


async def check_users_subset(
    db: AsyncSession,
    *,
    global_ids: list[int],
    force_refresh: bool = False,
) -> VipBatchStats:
    """Проверить список пользователей и посчитать изменения is_vip."""
    if not global_ids:
        return VipBatchStats(total=0, changed=0)

    total = 0
    changed = 0

    for global_id in global_ids:
        before = await _read_users_is_vip(db, global_id)
        res = await check_user_vip_once(
            db,
            global_id=global_id,
            force_refresh=force_refresh,
        )
        total += 1
        if before is None or res is None:
            continue
        after = await _read_users_is_vip(db, global_id)
        if after is not None and before != after:
            changed += 1

    return VipBatchStats(total=total, changed=changed)


async def check__all__users_once(
    db: AsyncSession,
    *,
    batch_size: int = VIP_CHECK_BATCH_SIZE,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Массовая проверка всех пользователей с ton_wallet (батчами)."""
    offset = 0
    total = 0
    changed_total = 0
    batches = 0

    stale_without_wallet = await _clear_stale_vip_without_wallet_sources(db)
    for global_id in stale_without_wallet:
        await _try_write_vip_log(
            db,
            global_id,
            old=True,
            new=False,
        )
    if stale_without_wallet:
        total += len(stale_without_wallet)
        changed_total += len(stale_without_wallet)
        await db.commit()

    while True:
        ids = await _fetch_global_ids_with_wallet_batch(
            db,
            offset=offset,
            limit=int(batch_size),
        )
        if not ids:
            break

        batches += 1
        before_map: dict[int, bool | None] = {}
        for global_id in ids:
            before_map[global_id] = await _read_users_is_vip(
                db,
                global_id,
            )

        await NftCheckService.sync_users_is_vip(
            db,
            ids,
            force_refresh=force_refresh,
        )

        for global_id in ids:
            after = await _read_users_is_vip(db, global_id)
            before = before_map.get(global_id)
            if before is None or after is None:
                continue
            if before != after:
                changed_total += 1

        total += len(ids)
        await db.commit()
        offset += len(ids)

    return {
        "total": total,
        "changed": changed_total,
        "batches": batches,
        "stale_without_wallet": len(stale_without_wallet),
    }


async def vip_health_snapshot(db: AsyncSession) -> dict[str, Any]:
    """Health-снимок canonical active verified wallet bindings."""
    all_sql = text(
        """
        SELECT COUNT(DISTINCT wb.global_id)
        FROM efhc_core.wallet_bindings wb
        WHERE wb.is_active = TRUE
          AND wb.proof_verified = TRUE
          AND wb.wallet_address IS NOT NULL
          AND LENGTH(TRIM(wb.wallet_address)) > 0
        """
    )
    vip_sql = text(
        """
        SELECT COUNT(*)
        FROM efhc_core.users
        WHERE is_vip = TRUE
        """
    )
    row_all: Result = await db.execute(all_sql)
    row_vip: Result = await db.execute(vip_sql)
    total_with_wallet = int(row_all.scalar() or 0)
    total_vip = int(row_vip.scalar() or 0)
    return {
        "with_wallet": total_with_wallet,
        "vip": total_vip,
        "collection": TON_NFT_COLLECTION or "",
    }


async def run_daily_vip_check() -> dict[str, Any]:
    """Обёртка планировщика: своя сессия и check__all__users_once."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        stats = await check__all__users_once(
            db,
            batch_size=VIP_CHECK_BATCH_SIZE,
            force_refresh=False,
        )
        await db.commit()
        logger.info("VIP daily check finished: %s", stats)
        return stats


__all__ = [
    "NftAsset",
    "NftCheckResult",
    "NftCheckError",
    "NftCheckService",
    "check_user_vip_once",
    "_fetch_wallet_candidates_batch",
    "check_users_subset",
    "check__all__users_once",
    "vip_health_snapshot",
    "run_daily_vip_check",
]
