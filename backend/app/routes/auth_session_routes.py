"""Provider-neutral session endpoints цикла 1618."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from app.deps import get_db
from app.identity.auth_context import AuthContext, AuthContextResponse
from app.identity.auth_dependencies import (
    get_auth_session_service,
    require_auth_context,
    require_auth_session_token,
)
from app.identity.auth_runtime_services import AuthSessionService
from app.identity.types import global_id_to_database
from app.identity.user_identities_storage_contract import (
    UserIdentityStatus,
)
from app.models.identity_models import UserIdentity
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])

class ProfilePhotoSourceResponse(BaseModel):
    """Безопасное описание provider photo без provider subject и credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    avatar_url: str
    is_primary: bool = False


class ProfilePhotoSourcesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ProfilePhotoSourceResponse, ...] = ()


def _safe_avatar_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 2048:
        return None
    if any(ord(ch) < 32 for ch in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return candidate


@router.get(
    "/session",
    response_model=AuthContextResponse,
    summary="Получить текущий provider-neutral auth context",
)
async def get_current_auth_session(
    response: Response,
    context: Annotated[AuthContext, Depends(require_auth_context)],
) -> AuthContextResponse:
    """Вернуть безопасный context без token и provider subject."""

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return AuthContextResponse.from_auth_context(context)


@router.get(
    "/profile-photos",
    response_model=ProfilePhotoSourcesResponse,
    summary="Получить доступные фотографии из подтверждённых провайдеров аккаунта",
)
async def get_profile_photo_sources(
    response: Response,
    context: Annotated[AuthContext, Depends(require_auth_context)],
    db: AsyncSession = Depends(get_db),
) -> ProfilePhotoSourcesResponse:
    """Вернуть только безопасные avatar URL из verified связанных identities.

    Provider subjects, auth tokens и полные provider metadata наружу не выдаются.
    """

    rows = (
        await db.execute(
            select(UserIdentity)
            .where(
                UserIdentity.global_id == global_id_to_database(context.global_id),
                UserIdentity.status == UserIdentityStatus.ACTIVE.value,
                UserIdentity.is_verified.is_(True),
            )
            .order_by(
                UserIdentity.is_primary.desc(),
                UserIdentity.updated_at.desc(),
                UserIdentity.id.desc(),
            )
        )
    ).scalars().all()

    by_provider: dict[str, ProfilePhotoSourceResponse] = {}
    for identity in rows:
        metadata = identity.provider_metadata
        if not isinstance(metadata, dict):
            continue
        avatar_url = _safe_avatar_url(
            metadata.get("avatar_url") or metadata.get("photo_url")
        )
        provider = str(identity.provider or "").strip()
        if not avatar_url or not provider or provider in by_provider:
            continue
        by_provider[provider] = ProfilePhotoSourceResponse(
            provider=provider,
            avatar_url=avatar_url,
            is_primary=bool(identity.is_primary),
        )

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ProfilePhotoSourcesResponse(items=tuple(by_provider.values()))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отозвать текущую server-side auth session",
)
async def logout_auth_session(
    token: Annotated[str, Depends(require_auth_session_token)],
    service: Annotated[
        AuthSessionService,
        Depends(get_auth_session_service),
    ],
) -> Response:
    """Атомарно отозвать bearer token без его логирования."""

    if not await service.revoke(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth session недействительна",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


__all__ = [
    "get_current_auth_session",
    "get_profile_photo_sources",
    "logout_auth_session",
    "router",
]
