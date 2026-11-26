# backend/app/services/admin/admin_rbac.py
"""RBAC админ-панели с каноническим actor owner ``global_id``."""

from __future__ import annotations

from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
S = get_settings()
EFHC_SUPERADMIN_GLOBAL_ID = 88  # OWNER release canon; ID is public, not a credential.

SCHEMA_ADMIN: str = canon_schema(
    getattr(S, "DB_SCHEMA_ADMIN", "efhc_admin") or "efhc_admin",
)


class AdminRole(str):
    """Роли администраторов, используемые service layer."""

    SUPERADMIN = "SuperAdmin"
    MODERATOR = "Moderator"
    ANALYST = "Analyst"


_ROLE_LEVEL: dict[str, int] = {
    AdminRole.ANALYST: 1,
    AdminRole.MODERATOR: 2,
    AdminRole.SUPERADMIN: 3,
}
_DB_ROLE_MAP = {
    "auditor": AdminRole.ANALYST,
    "support": AdminRole.MODERATOR,
    "admin": AdminRole.MODERATOR,
    "superadmin": AdminRole.SUPERADMIN,
    "Analyst": AdminRole.ANALYST,
    "Moderator": AdminRole.MODERATOR,
    "SuperAdmin": AdminRole.SUPERADMIN,
}


class AdminAuthError(PermissionError):
    """Ошибка авторизации/прав администратора."""


class AdminUser(BaseModel):
    """Администратор business layer.

    ``global_id`` — actor owner. ``tg_id`` — необязательный Telegram
    provider subject, используемый только для delivery/diagnostics.
    """

    id: int = Field(..., description="Локальный PK whitelist")
    global_id: int = Field(..., ge=1, le=9_999_999_999)
    tg_id: int | None = None
    role: str
    is_active: bool = Field(default=True)


class RBAC:
    """Проверка прав по каноническому ``global_id`` администратора."""

    @staticmethod
    def _normalize_role(role_raw: str) -> str:
        role = (role_raw or "").strip()
        normalized = _DB_ROLE_MAP.get(role, role)
        if normalized not in _ROLE_LEVEL:
            raise AdminAuthError(
                f"Неизвестная роль администратора: {role!r}"
            )
        return normalized

    @staticmethod
    def _level(role: str) -> int:
        return _ROLE_LEVEL.get(role, 0)

    @staticmethod
    async def resolve_admin(
        db: AsyncSession,
        global_id: int,
    ) -> AdminUser:
        """Разрешить active whitelist entry по canonical owner."""

        if int(global_id) != EFHC_SUPERADMIN_GLOBAL_ID:
            raise AdminAuthError("EFHC_ADMIN_GLOBAL_ID_FORBIDDEN")
        if not 1 <= int(global_id) <= 9_999_999_999:
            raise AdminAuthError(
                "Некорректный global_id администратора"
            )
        admin = await RBAC._fetch_admin_from_db(db, int(global_id))
        if admin is None:
            raise AdminAuthError("Администратор не найден или отключён")
        return admin

    @staticmethod
    async def _fetch_admin_from_db(
        db: AsyncSession,
        global_id: int,
    ) -> AdminUser | None:
        sql = text(
            """
SELECT
    aw.id,
    aw.global_id,
    aw.tg_id,
    (
        SELECT ar.role::text
        FROM efhc_admin.admin_role AS ar
        WHERE ar.admin_id = aw.id
        ORDER BY
            CASE ar.role::text
                WHEN 'superadmin' THEN 3
                WHEN 'admin' THEN 2
                WHEN 'support' THEN 2
                WHEN 'auditor' THEN 1
                ELSE 0
            END DESC,
            ar.created_at ASC
        LIMIT 1
    ) AS role,
    COALESCE(aw.is_active, TRUE) AS is_active
FROM efhc_admin.admin_whitelist AS aw
JOIN efhc_core.users AS u
  ON u.global_id = aw.global_id
 AND u.is_active IS TRUE
WHERE aw.global_id = :global_id
LIMIT 1
"""
        )
        try:
            result: Result = await db.execute(
                sql,
                {"global_id": int(global_id)},
            )
            row = result.fetchone()
        except Exception as exc:
            logger.error(
                "RBAC: DB error while resolving global_id=%s: %s",
                global_id,
                exc,
            )
            raise
        if not row or not bool(getattr(row, "is_active", True)):
            return None
        if getattr(row, "role", None) is None:
            raise AdminAuthError(
                "Администратору не назначена явная RBAC-роль"
            )
        role = RBAC._normalize_role(str(row.role))
        return AdminUser(
            id=int(row.id),
            global_id=int(row.global_id),
            tg_id=(
                int(row.tg_id)
                if getattr(row, "tg_id", None) is not None
                else None
            ),
            role=role,
            is_active=True,
        )

    @staticmethod
    async def try_resolve_admin(
        db: AsyncSession,
        global_id: int,
    ) -> AdminUser | None:
        try:
            return await RBAC.resolve_admin(db, global_id)
        except AdminAuthError as exc:
            logger.info("RBAC.try_resolve_admin: denied: %s", exc)
            return None

    @staticmethod
    async def resolve_admin_nft(
        db: AsyncSession,
        global_id: int,
    ) -> AdminUser | None:
        """Разрешить резервный Admin NFT-доступ через ``ton_wallet_id``.

        ``global_id`` берётся только из проверенной server-side session.
        Далее проверенная TON identity этого аккаунта сопоставляется с
        материализованным результатом штатной NFT-проверки. Источник права —
        точный Admin NFT-item address из TON_ADMIN_NFT_IDS внутри VIP-коллекции; строка БД сама по
        себе права не выдаёт. ``ton_wallet_id`` остаётся provider subject.
        """

        if int(global_id) != EFHC_SUPERADMIN_GLOBAL_ID:
            return None
        if not 1 <= int(global_id) <= 9_999_999_999:
            return None
        configured_nft_ids = {
            str(value).strip()
            for value in (getattr(S, "TON_ADMIN_NFT_IDS", []) or [])
            if str(value).strip()
        }
        if not configured_nft_ids:
            return None
        result: Result = await db.execute(
            text(
                """
SELECT nft.id, ui.global_id, nft.role, nft.nft_id, nft.is_active
FROM efhc_admin.admin_nft_whitelist AS nft
JOIN efhc_core.user_identities AS ui
  ON ui.provider = 'ton'
 AND ui.provider_subject = nft.ton_wallet_id
JOIN efhc_core.users AS u
  ON u.global_id = ui.global_id
 AND u.is_active IS TRUE
WHERE ui.global_id = :global_id
  AND ui.status = 'active'
  AND ui.is_verified = TRUE
  AND ui.verified_at IS NOT NULL
  AND nft.source = 'env_nft'
  AND nft.nft_id IS NOT NULL
  AND nft.is_active = TRUE
  AND nft.revoked_at IS NULL
  AND nft.updated_at >= NOW() - (:max_age * INTERVAL '1 second')
ORDER BY ui.is_primary DESC, ui.verified_at DESC, nft.id ASC
LIMIT 1
"""
            ),
            {
                "global_id": int(global_id),
                "max_age": int(
                    getattr(S, "NFT_CACHE_TTL_SECONDS", 900) or 900
                ),
            },
        )
        row = result.fetchone()
        if row is None:
            return None
        if str(row.nft_id or "").strip() not in configured_nft_ids:
            return None
        role = RBAC._normalize_role(str(row.role or "admin"))
        return AdminUser(
            id=int(row.id),
            global_id=int(row.global_id),
            tg_id=None,
            role=role,
            is_active=True,
        )

    @staticmethod
    def require_role(admin: AdminUser, minimal: str) -> None:
        if admin.global_id != EFHC_SUPERADMIN_GLOBAL_ID or admin.role != AdminRole.SUPERADMIN:
            raise AdminAuthError("EFHC_ADMIN_OWNER_ONLY")
        minimal_norm = RBAC._normalize_role(minimal)
        admin_level = RBAC._level(admin.role)
        need_level = RBAC._level(minimal_norm)
        if admin_level < need_level:
            raise AdminAuthError(
                f"Недостаточно прав: нужен >= {minimal_norm}, "
                f"у администратора {admin.role}"
            )

    @staticmethod
    def admin_from_auth_context(auth: Any) -> AdminUser:
        """Построить canonical principal из уже проверенного Admin gate.

        Центральный ``require_admin_or_nft_or_key`` уже выполнил весь
        authentication/access resolution, включая обычный whitelist и Admin
        NFT. Повторный вызов ``resolve_admin`` после этого запрещён: он
        whitelist-only и исторически ломал законный Admin NFT access.

        Этот helper НЕ является новым способом авторизации. Он только переносит
        уже разрешённые ``global_id/admin_id/role`` в service-layer DTO.
        """

        try:
            global_id = int(auth.global_id)
            admin_id = int(auth.admin_id)
            role = RBAC._normalize_role(str(auth.role))
        except (AttributeError, TypeError, ValueError) as exc:
            raise AdminAuthError(
                "Некорректный проверенный Admin principal"
            ) from exc
        if global_id != EFHC_SUPERADMIN_GLOBAL_ID or role != AdminRole.SUPERADMIN:
            raise AdminAuthError("EFHC_ADMIN_OWNER_ONLY")
        return AdminUser(
            id=admin_id,
            global_id=global_id,
            tg_id=None,
            role=role,
            is_active=True,
        )

    @staticmethod
    def is_superadmin(admin: AdminUser) -> bool:
        """Вернуть только факт уже разрешённой роли SuperAdmin.

        Решение цикла 1728 для будущих аудитов: helper сохраняется как
        стабильный compatibility/public convenience API, но НИКОГДА не является
        вторым способом авторизации. Перед ним администратор уже должен быть
        получен через канонический resolve_admin/require_role либо законный
        Admin NFT access-contour. Нельзя использовать этот bool-helper для
        обхода whitelist, RBAC, session/global_id или NFT-проверки.
        """
        return admin.global_id == EFHC_SUPERADMIN_GLOBAL_ID and admin.role == AdminRole.SUPERADMIN


__all__ = [
    "AdminAuthError",
    "AdminRole",
    "AdminUser",
    "RBAC",
]
