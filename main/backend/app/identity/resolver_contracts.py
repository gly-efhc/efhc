"""Контракты fail-closed IdentityResolver EFHC."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from app.identity.auth_errors import InvalidIdentityResolution
from app.identity.types import GlobalId
from app.identity.verified_identity import VerifiedIdentity

_RESOLUTION_MARKER = object()


# Сохраняем историческую str+Enum семантику resolver contract.
class IdentityResolutionStatus(str, Enum):  # noqa: UP042
    """Fail-closed результат lookup проверенной provider identity."""

    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"


# Сохраняем str+Enum wire-семантику machine contract.
class IdentityConflictCode(str, Enum):  # noqa: UP042
    """Безопасная причина отказа без выбора global account."""

    STORAGE_CONFLICT = "storage_conflict"
    MULTIPLE_MATCHES = "multiple_matches"
    IDENTITY_INACTIVE = "identity_inactive"
    IDENTITY_UNVERIFIED = "identity_unverified"
    INVALID_GLOBAL_ID = "invalid_global_id"
    PROVIDER_NOT_STORABLE = "provider_not_storable"
    SUBJECT_NOT_STORABLE = "subject_not_storable"


@dataclass(frozen=True, slots=True, init=False)
class IdentityResolution:
    """Результат resolver без account creation или auto-merge."""

    status: IdentityResolutionStatus
    global_id: GlobalId | None
    conflict_code: IdentityConflictCode | None

    def __init__(
        self,
        *,
        status: IdentityResolutionStatus,
        global_id: GlobalId | None,
        conflict_code: IdentityConflictCode | None = None,
        _marker: object | None = None,
    ) -> None:
        if _marker is not _RESOLUTION_MARKER:
            raise InvalidIdentityResolution()
        if not isinstance(status, IdentityResolutionStatus):
            raise InvalidIdentityResolution()
        if status is IdentityResolutionStatus.RESOLVED:
            if not isinstance(global_id, GlobalId):
                raise InvalidIdentityResolution()
            if conflict_code is not None:
                raise InvalidIdentityResolution()
        elif status is IdentityResolutionStatus.NOT_FOUND:
            if global_id is not None or conflict_code is not None:
                raise InvalidIdentityResolution()
        else:
            if global_id is not None:
                raise InvalidIdentityResolution()
            if not isinstance(conflict_code, IdentityConflictCode):
                raise InvalidIdentityResolution()
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "global_id", global_id)
        object.__setattr__(self, "conflict_code", conflict_code)

    @classmethod
    def resolved(cls, global_id: GlobalId) -> IdentityResolution:
        """Создать успешный результат только с nominal GlobalId."""

        return cls(
            status=IdentityResolutionStatus.RESOLVED,
            global_id=global_id,
            conflict_code=None,
            _marker=_RESOLUTION_MARKER,
        )

    @classmethod
    def not_found(cls) -> IdentityResolution:
        """Создать явный результат отсутствующей identity."""

        return cls(
            status=IdentityResolutionStatus.NOT_FOUND,
            global_id=None,
            conflict_code=None,
            _marker=_RESOLUTION_MARKER,
        )

    @classmethod
    def conflict(
        cls,
        code: IdentityConflictCode = (
            IdentityConflictCode.STORAGE_CONFLICT
        ),
    ) -> IdentityResolution:
        """Создать fail-closed conflict без выбора аккаунта."""

        if not isinstance(code, IdentityConflictCode):
            raise InvalidIdentityResolution()
        return cls(
            status=IdentityResolutionStatus.CONFLICT,
            global_id=None,
            conflict_code=code,
            _marker=_RESOLUTION_MARKER,
        )


@runtime_checkable
class IdentityResolver(Protocol):
    """Resolver принимает только уже проверенную provider identity."""

    async def resolve_verified_identity(
        self,
        identity: VerifiedIdentity,
    ) -> IdentityResolution:
        """Разрешить identity без create, merge или session issue."""
