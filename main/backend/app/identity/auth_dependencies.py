"""FastAPI dependencies provider-neutral auth-core цикла 1613."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from app.core.database_core import get_session_factory
from app.identity.auth_context import AuthContext
from app.identity.auth_errors import (
    AuthRoleDenied,
    AuthSessionNotActive,
    InvalidAuthRuntimeInput,
)
from app.identity.auth_runtime_services import (
    AuthSessionService,
    validate_auth_role,
)
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def get_auth_session_service() -> AuthSessionService:
    """Построить service поверх канонической session factory."""

    return AuthSessionService(get_session_factory())


def _unauthorized_session() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Auth session недействительна",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth_session_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> str:
    """Вернуть raw bearer только внутреннему logout/session boundary."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized_session()
    token = credentials.credentials
    if not isinstance(token, str) or not token:
        raise _unauthorized_session()
    return token


async def get_optional_auth_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
    service: Annotated[
        AuthSessionService,
        Depends(get_auth_session_service),
    ],
) -> AuthContext | None:
    """Вернуть None без credentials, но invalid token закрыть 401."""

    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise _unauthorized_session()
    try:
        return await service.authenticate(credentials.credentials)
    except (AuthSessionNotActive, InvalidAuthRuntimeInput) as exc:
        raise _unauthorized_session() from exc


async def require_auth_context(
    context: Annotated[
        AuthContext | None,
        Depends(get_optional_auth_context),
    ],
) -> AuthContext:
    """Потребовать active hashed server-side session."""

    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется аутентификация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return context


AuthDependency = Callable[[AuthContext], Awaitable[AuthContext]]


def require_auth_roles(*required_roles: str) -> AuthDependency:
    """Создать dependency, проверяющую provider-neutral roles."""

    if not required_roles:
        raise ValueError("Требуется непустой набор auth roles")
    try:
        required = frozenset(
            validate_auth_role(role) for role in required_roles
        )
    except InvalidAuthRuntimeInput as exc:
        raise ValueError("Auth role имеет недопустимый формат") from exc

    async def _dependency(
        context: Annotated[
            AuthContext,
            Depends(require_auth_context),
        ],
    ) -> AuthContext:
        if not required.issubset(context.roles):
            denied = AuthRoleDenied()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=denied.message,
            ) from denied
        return context

    return _dependency


__all__ = [
    "get_auth_session_service",
    "get_optional_auth_context",
    "require_auth_context",
    "require_auth_session_token",
    "require_auth_roles",
]
