"""Provider-neutral TON login endpoints циклов 1615–1618."""

from __future__ import annotations

import hashlib

from app.core.config_core import get_settings
from app.core.database_core import get_session_factory
from app.identity.auth_errors import (
    AuthChallengeRateLimited,
    AuthProviderError,
)
from app.identity.auth_runtime_services import AuthChallengeService
from app.identity.referral_ingress import (
    ReferralIngressError,
    parse_referral_start_param,
)
from app.identity.ton_account_registration import (
    TonAccountRegistrationError,
)
from app.identity.ton_auth_session import (
    TonAuthSessionError,
    TonAuthSessionService,
)
from app.identity.ton_login_challenge import (
    TonLoginChallengeService,
    TonLoginDomainError,
    resolve_ton_login_domain,
)
from app.identity.ton_proof_verification import (
    TonApiStateInitResolver,
    TonProofData,
    TonProofVerificationError,
    TonProofVerificationService,
)
from app.schemas.auth_ton_schemas import (
    AuthSessionCredentialOut,
    TonLoginChallengeOut,
    TonLoginProofIn,
    TonLoginProofOut,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)

router = APIRouter(prefix="/auth/ton", tags=["auth", "ton"])


def _error_detail(
    *,
    error: str,
    message: str,
    reason: str | None = None,
) -> dict[str, object]:
    """Сформировать HTTP error envelope."""

    details: dict[str, str] = {}
    if reason is not None:
        details["reason"] = reason
    return {
        "error": error,
        "message": message,
        "details": details,
    }


def _ton_challenge_client_fingerprint(request: Request) -> str:
    """Получить необратимый storage fingerprint transport-клиента."""

    host = request.client.host if request.client is not None else "unknown"
    material = f"efhc.ton.challenge.client.v1\x00{host}".encode()
    return hashlib.sha256(material).hexdigest()


def get_ton_login_challenge_service(
    request: Request,
) -> TonLoginChallengeService:
    """Создать DB-backed rate-limited TON challenge service."""

    settings = get_settings()
    auth_service = AuthChallengeService(
        get_session_factory(),
        issuance_fingerprint=_ton_challenge_client_fingerprint(request),
        rate_limit_window_sec=int(
            settings.TON_AUTH_CHALLENGE_RATE_WINDOW_SEC
        ),
        rate_limit_max_requests=int(
            settings.TON_AUTH_CHALLENGE_RATE_MAX_REQUESTS
        ),
        max_outstanding=int(settings.TON_AUTH_CHALLENGE_MAX_OUTSTANDING),
        cleanup_batch=int(settings.TON_AUTH_CHALLENGE_CLEANUP_BATCH),
    )
    return TonLoginChallengeService.from_auth_service(auth_service)


def get_ton_auth_session_service() -> TonAuthSessionService:
    """Создать transactional TON account/session service."""

    return TonAuthSessionService(get_session_factory())


def get_ton_proof_verification_service() -> TonProofVerificationService:
    """Создать verifier с authoritative TonAPI resolver."""

    settings = get_settings()
    challenge_service = AuthChallengeService(get_session_factory())
    key_resolver = TonApiStateInitResolver(
        base_url=str(settings.TON_API_BASE_URL),
        api_key=str(settings.TON_API_KEY),
        configured_network=str(settings.TON_NETWORK),
    )
    return TonProofVerificationService(
        challenge_consumer=challenge_service,
        key_resolver=key_resolver,
        configured_network=str(settings.TON_NETWORK),
    )


def get_ton_login_domain(request: Request) -> str:
    """Определить domain без Telegram context."""

    settings = get_settings()
    return str(
        resolve_ton_login_domain(
            environment=getattr(settings, "ENV", "local"),
            app_url=getattr(settings, "APP_URL", ""),
            frontend_url=getattr(settings, "FRONTEND_URL", ""),
            request_hostname=request.url.hostname or "",
        )
    )


def require_ton_login_enabled() -> None:
    """Отсутствующий feature flag означает deny."""

    settings = get_settings()
    runtime_flags = dict(
        getattr(settings, "AUTH_PROVIDER_FLAGS", {}) or {}
    )
    test_flags = dict(
        getattr(settings, "AUTH_PROVIDER_TEST_FLAGS", {}) or {}
    )
    env = str(getattr(settings, "ENV", "local") or "local").lower()
    active = test_flags if env in {"ci", "test"} else runtime_flags
    if active.get("ton") is not True:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                error="auth.provider_disabled",
                message="TON login provider отключён",
            ),
        )


@router.post(
    "/challenge",
    response_model=TonLoginChallengeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Выдать one-time challenge для TON login",
)
async def issue_ton_login_challenge(
    response: Response,
    domain: str = Depends(get_ton_login_domain),
    _enabled: None = Depends(require_ton_login_enabled),
    service: TonLoginChallengeService = Depends(
        get_ton_login_challenge_service
    ),
) -> TonLoginChallengeOut:
    """Выдать challenge без Telegram и auth side effects."""

    try:
        issued = await service.issue(domain=domain)
    except AuthChallengeRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
            ),
        ) from exc
    except TonLoginDomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc
    except AuthProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
            ),
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TonLoginChallengeOut(
        challenge_id=issued.challenge_id,
        payload=issued.payload,
        expires_at=issued.expires_at,
        domain=issued.domain,
    )


@router.post(
    "/proof",
    response_model=TonLoginProofOut,
    summary="Проверить TON Proof и выдать auth session",
)
async def verify_ton_login_proof(
    body: TonLoginProofIn,
    response: Response,
    domain: str = Depends(get_ton_login_domain),
    _enabled: None = Depends(require_ton_login_enabled),
    service: TonProofVerificationService = Depends(
        get_ton_proof_verification_service
    ),
    auth_service: TonAuthSessionService = Depends(
        get_ton_auth_session_service
    ),
) -> TonLoginProofOut:
    """Проверить proof и атомарно выдать global account session."""

    try:
        referral_ingress = parse_referral_start_param(
            body.referral_start_param
        )
    except ReferralIngressError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc

    try:
        verified = await service.verify(
            challenge_id=body.challenge_id,
            address=body.ton_wallet_id,
            network=body.network,
            public_key=body.public_key,
            proof=TonProofData(
                timestamp=body.proof.timestamp,
                domain_length_bytes=body.proof.domain.length_bytes,
                domain=body.proof.domain.value,
                signature=body.proof.signature,
                payload=body.proof.payload,
                state_init=body.proof.state_init,
            ),
            expected_domain=domain,
        )
    except TonProofVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc
    try:
        if referral_ingress.normalized_code is None:
            login = await auth_service.login(verified)
        else:
            login = await auth_service.login(
                verified,
                referral_start_param=(
                    referral_ingress.normalized_code
                ),
            )
    except TonAccountRegistrationError as exc:
        status_code = status.HTTP_409_CONFLICT
        if exc.reason in {
            "REFERRAL_CODE_NOT_FOUND",
            "REFERRAL_CODE_INVALID",
        }:
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc
    except TonAuthSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TonLoginProofOut(
        challenge_id=verified.challenge_id,
        ton_wallet_id=verified.ton_wallet_id,
        network=verified.network,
        verified_at=verified.verified_at,
        global_id=login.account.global_id.display,
        account_outcome=login.account.outcome,
        session=AuthSessionCredentialOut(
            access_token=login.session.token,
            expires_at=login.session.expires_at,
        ),
    )


__all__ = [
    "get_ton_auth_session_service",
    "get_ton_login_challenge_service",
    "get_ton_login_domain",
    "get_ton_proof_verification_service",
    "issue_ton_login_challenge",
    "require_ton_login_enabled",
    "router",
    "verify_ton_login_proof",
]
