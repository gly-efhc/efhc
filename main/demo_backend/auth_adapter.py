"""Isolated operator sessions plus genuine server-issued TON/Telegram sessions.

DEMO operator tokens are private to this process. Real provider tokens are
validated by the unmodified backend against the *Neon TEST* auth_sessions
and user_identities tables. No fabricated TON Proof result is ever accepted.
"""
from __future__ import annotations

from demo_backend.session_store import DemoSessionStore

_native_authenticate = None


def install_demo_auth(store: DemoSessionStore) -> None:
    from app.identity.auth_context import AuthContext
    from app.identity.auth_errors import AuthSessionNotActive
    from app.identity.auth_provider import AuthProvider
    from app.identity.auth_runtime_services import AuthSessionService
    from app.identity.types import GlobalId
    from app.identity.verified_identity import _restore_verified_identity_from_storage

    global _native_authenticate
    if getattr(AuthSessionService.authenticate, "_efhc_demo_wrapper", False):
        raise RuntimeError("Demo auth bridge installed more than once")
    original = AuthSessionService.authenticate
    original_revoke = AuthSessionService.revoke
    _native_authenticate = original

    async def authenticate(self, token: object) -> AuthContext:
        demo = store.get(token if isinstance(token, str) else None)
        if demo is not None:
            verified = _restore_verified_identity_from_storage(
                AuthProvider.MOCK, f"efhc-demo-operator:{demo.global_id}"
            )
            return AuthContext(
                global_id=GlobalId.from_external(demo.global_id),
                verified_identity=verified,
                # Server-attested, unprivileged UI-only scope. Neither Admin\n                # role nor verified Telegram identity is granted here.\n                roles=frozenset({"user", "test_visual"})\n                if demo.scope == "visual" else frozenset({"user"}),
                session_id=None,
            )
        # This is a native token issued by the same backend from a verified
        # Telegram / TonConnect login, never a browser-selected identity.
        return await original(self, token)

    async def revoke(self, token: object) -> bool:
        if isinstance(token, str) and store.get(token) is not None:
            return store.revoke(token)
        return await original_revoke(self, token)

    authenticate._efhc_demo_wrapper = True  # type: ignore[attr-defined]
    AuthSessionService.authenticate = authenticate  # type: ignore[assignment]
    AuthSessionService.revoke = revoke  # type: ignore[assignment]


async def authenticate_native_session(token: str):
    """Preflight real auth bearer against TEST DB, without mock fallback."""
    if _native_authenticate is None:
        raise RuntimeError("Demo auth adapter not initialized")
    from app.core.database_core import get_session_factory
    from app.identity.auth_runtime_services import AuthSessionService
    service = AuthSessionService(get_session_factory())
    return await _native_authenticate(service, token)
