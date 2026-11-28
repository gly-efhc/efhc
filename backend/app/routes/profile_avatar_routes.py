"""Global ID owned avatar preference: no binaries, no server image fetching.

The preference is a namespaced, revisioned value of the existing users.meta
JSONB column. This keeps the frozen 0001 PostgreSQL schema unchanged.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from app.deps import get_db
from app.identity.auth_context import AuthContext
from app.identity.auth_dependencies import require_auth_context
from app.identity.types import global_id_to_database
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/profile/avatar", tags=["profile-avatar"])
META_KEY = "avatar_preference_v1"
AvatarIcon = Literal["EI-07"]


def validate_https_avatar_url(value: str) -> str:
    """Validate lexically; never make a backend GET/HEAD to user URL."""
    if not isinstance(value, str):
        raise ValueError("invalid_avatar_url")
    value = value.strip()
    if (not value or len(value) > 2048 or "\\" in value
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127
                   for ch in value)):
        raise ValueError("invalid_avatar_url")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        if (parsed.scheme.lower() != "https" or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or "@" in parsed.netloc):
            raise ValueError("invalid_avatar_url")
    except ValueError as exc:
        raise ValueError("invalid_avatar_url") from exc
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProviderChoice(StrictModel):
    kind: Literal["provider"]
    identityId: str = Field(pattern=r"^[1-9][0-9]{0,18}$")

    @field_validator("identityId")
    @classmethod
    def check_identity_id(cls, value: str) -> str:
        if int(value) > 9223372036854775807:
            raise ValueError("invalid_identity_id")
        return value


class UrlChoice(StrictModel):
    kind: Literal["url"]
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return validate_https_avatar_url(value)


class IconChoice(StrictModel):
    kind: Literal["icon"]


class SystemChoice(StrictModel):
    kind: Literal["system"]
    systemId: str = Field(pattern=r"^avatar-(0[1-9]|10)$")


Selection = Annotated[
    ProviderChoice | UrlChoice | IconChoice | SystemChoice,
    Field(discriminator="kind"),
]


class AvatarPreference(StrictModel):
    schemaVersion: Literal[1]
    selection: Selection
    fallbackIcon: AvatarIcon


class AvatarUpdate(StrictModel):
    preference: AvatarPreference
    expectedRevision: int = Field(ge=0)


class AvatarEnvelope(StrictModel):
    preference: AvatarPreference
    revision: int
    updatedAt: str | None


class AvatarSource(StrictModel):
    identityId: str
    provider: str
    label: str
    avatarUrl: str | None
    status: Literal[
        "available", "no_photo", "unsupported", "reauth_required"
    ]
    photoRevision: str


class AvatarSources(StrictModel):
    items: list[AvatarSource]


def _default_preference(identities: list[UserIdentity]) -> AvatarPreference:
    """Use verified Telegram photo only on first initialized preference."""
    verified_telegram = next(
        (item for item in identities
         if item.provider == "telegram"
         and item.status == "active" and item.is_verified
         and _identity_image(item)),
        None,
    )
    selection: Selection = (
        ProviderChoice(kind="provider", identityId=str(verified_telegram.id))
        if verified_telegram is not None else IconChoice(kind="icon")
    )
    return AvatarPreference(
        schemaVersion=1, selection=selection, fallbackIcon="EI-07"
    )


def _identity_image(identity: UserIdentity) -> str | None:
    if identity.provider == "apple":
        return None
    metadata = identity.provider_metadata
    if not isinstance(metadata, dict):
        return None
    for key in ("avatar_url", "photo_url"):
        candidate = metadata.get(key)
        if not isinstance(candidate, str):
            continue
        try:
            return validate_https_avatar_url(candidate)
        except ValueError:
            continue
    return None


def _read_saved(value: object) -> AvatarEnvelope | None:
    if not isinstance(value, dict):
        return None
    try:
        # Retired EI images are gone; migrate only the icon field, preserving
        # provider selection, revision, update timestamp and ownership.
        candidate = dict(value)
        preference = candidate.get("preference")
        if isinstance(preference, dict):
            candidate["preference"] = {**preference, "fallbackIcon": "EI-07"}
        return AvatarEnvelope.model_validate(candidate)
    except ValueError:
        # Corrupt legacy metadata must not become a forged image URL.
        return None


async def _identities(db: AsyncSession, owner: int) -> list[UserIdentity]:
    query = select(UserIdentity).where(
        UserIdentity.global_id == owner,
        UserIdentity.is_verified.is_(True),
        UserIdentity.status == "active",
    ).order_by(UserIdentity.is_primary.desc(), UserIdentity.id)
    return list((await db.execute(query)).scalars().all())


def _envelope(user: User, identities: list[UserIdentity]) -> AvatarEnvelope:
    saved = _read_saved((user.meta or {}).get(META_KEY))
    return saved or AvatarEnvelope(
        preference=_default_preference(identities), revision=0,
        updatedAt=None,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get("", response_model=AvatarEnvelope)
async def get_avatar(
    response: Response,
    context: Annotated[AuthContext, Depends(require_auth_context)],
    db: AsyncSession = Depends(get_db),
) -> AvatarEnvelope:
    owner = global_id_to_database(context.global_id)
    user = await db.scalar(select(User).where(User.global_id == owner))
    if user is None:
        raise HTTPException(status_code=404, detail="profile_unavailable")
    result = _envelope(user, await _identities(db, owner))
    _no_store(response)
    return result


@router.get("/sources", response_model=AvatarSources)
async def get_avatar_sources(
    response: Response,
    context: Annotated[AuthContext, Depends(require_auth_context)],
    db: AsyncSession = Depends(get_db),
) -> AvatarSources:
    owner = global_id_to_database(context.global_id)
    rows = await _identities(db, owner)
    items: list[AvatarSource] = []
    for identity in rows:
        src = _identity_image(identity)
        unsupported = identity.provider in {"apple", "ton"}
        items.append(AvatarSource(
            identityId=str(identity.id),
            provider=identity.provider,
            label=identity.provider,
            avatarUrl=src,
            status=("unsupported" if unsupported
                    else "available" if src else "no_photo"),
            photoRevision=str(identity.updated_at or "0"),
        ))
    _no_store(response)
    return AvatarSources(items=items)


@router.put("", response_model=AvatarEnvelope)
async def put_avatar(
    payload: AvatarUpdate,
    response: Response,
    context: Annotated[AuthContext, Depends(require_auth_context)],
    db: AsyncSession = Depends(get_db),
) -> AvatarEnvelope:
    owner = global_id_to_database(context.global_id)
    # Lock the owning row for the entire preference revision transaction.
    user = await db.scalar(
        select(User).where(User.global_id == owner).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="profile_unavailable")
    identities = await _identities(db, owner)
    previous = _envelope(user, identities)
    if previous.revision != payload.expectedRevision:
        raise HTTPException(status_code=409, detail="avatar_revision_conflict")
    selected = payload.preference.selection
    if selected.kind == "provider":
        # Guard the selected identity under a lock, not only from GET cache.
        identity = await db.scalar(
            select(UserIdentity).where(
                UserIdentity.id == int(selected.identityId),
                UserIdentity.global_id == owner,
                UserIdentity.status == "active",
                UserIdentity.is_verified.is_(True),
            ).with_for_update()
        )
        if identity is None:
            raise HTTPException(
                status_code=422, detail="avatar_identity_unavailable"
            )
    if selected.kind == "system":
        # All existing system slots are reserved/unavailable.
        raise HTTPException(
            status_code=422, detail="avatar_system_unavailable"
        )
    result = AvatarEnvelope(
        preference=payload.preference, revision=previous.revision + 1,
        updatedAt=datetime.now(UTC).isoformat(),
    )
    meta = dict(user.meta or {})
    meta[META_KEY] = result.model_dump(mode="json")
    user.meta = meta
    await db.commit()
    _no_store(response)
    return result
