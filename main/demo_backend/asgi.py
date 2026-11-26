"""Isolated FastAPI DEMO entrypoint: original EFHC routes, Neon TEST.

Run only as `uvicorn demo_backend.asgi:app` from a tree where unmodified
`backend/` is a sibling of `demo_backend/`. Never run as `app.main:app` for DEMO.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path

from demo_backend.config import DemoConfig, prepare_backend_environment
from demo_backend.session_store import DemoSessionStore

CONFIG = DemoConfig.from_env()
prepare_backend_environment(CONFIG)
_backend_path = Path(__file__).resolve().parent.parent / "backend"
if not (_backend_path / "app" / "main.py").is_file():
    raise RuntimeError("Unmodified EFHC backend/ is required next to demo_backend/")
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from app.main import app  # noqa: E402
from app.core.config_core import get_settings  # noqa: E402
from app.core.database_core import db_session  # noqa: E402
from demo_backend.auth_adapter import install_demo_auth, authenticate_native_session  # noqa: E402
from demo_backend.schema import inspect_schema, check_user, assert_completed_genesis  # noqa: E402
from demo_backend.account_guards import is_safe_synthetic_account  # noqa: E402
from demo_backend.preview_access import install_preview_admin, test_admin_lease_active  # noqa: E402
from demo_backend.env_admin import authorized_test_admin, install_admin_role_compatibility  # noqa: E402
from demo_backend.visual_admin_read import visual_admin_report_allowed  # noqa: E402
from demo_backend.routes import DemoRoutes  # noqa: E402
from demo_backend.scheduler import periodic_energy  # noqa: E402
from demo_backend.tonconnect import (install_test_tonconnect_binding, genesis_guest_wallet_route)  # noqa: E402
from app.routes.auth_telegram_routes import get_telegram_auth_session_service  # noqa: E402
from demo_backend.telegram_owner_binding import get_demo_telegram_owner_binding_service  # noqa: E402
from fastapi import Request  # noqa: E402
from app.identity.auth_errors import AuthSessionNotActive, InvalidAuthRuntimeInput  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402

log = logging.getLogger("efhc.demo_backend")
SESSIONS = DemoSessionStore()
install_demo_auth(SESSIONS)
install_admin_role_compatibility(CONFIG)
# Isolated TEST process only: real Admin routes, preview data and actions.
install_preview_admin(app, SESSIONS, CONFIG)
# TEST-only override; native production dependency is untouched.
app.dependency_overrides[get_telegram_auth_session_service] = get_demo_telegram_owner_binding_service
install_test_tonconnect_binding(app, SESSIONS)
app.include_router(DemoRoutes(CONFIG, SESSIONS).router)

from demo_backend.security import is_external_blocked  # noqa: E402

@app.middleware("http")
async def demo_isolation(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    method = request.method.upper()
    if method == "OPTIONS":
        return await call_next(request)
    origin = request.headers.get("origin")
    if origin and origin not in CONFIG.cors_origins:
        return JSONResponse({"detail": "DEMO_ORIGIN_FORBIDDEN"}, status_code=403)
    # Retain original external integrations (including TON Proof). The real
    # underlying backend verifies proofs, source signatures and credentials.
    if is_external_blocked(method, path):
        return JSONResponse({"detail": "DEMO_UNSUPPORTED_OPERATION"}, status_code=409)
    # TON/Telegram login endpoints are public by contract: they perform their
    # *own* verification, then issue a native Neon TEST auth session.
    public = path in {
        "/api/staging/login", "/api/staging/guest", "/api/staging/health", "/api/staging/visual-access", "/meta/health_db",
        "/openapi.json", "/docs", "/redoc",
        "/api/auth/ton/challenge", "/api/auth/ton/proof",
        "/api/auth/telegram/session",
    }
    env_admin_approved = False
    if path.startswith("/api/") and not public:
        auth = request.headers.get("authorization", "")
        header_token = auth[7:] if auth.startswith("Bearer ") else None
        cookie_token = request.cookies.get(CONFIG.cookie_name)
        token = header_token or cookie_token
        operator_session = SESSIONS.get(token)
        if operator_session is not None:
            if operator_session.scope == "visual" and not CONFIG.visual_access_active:
                SESSIONS.revoke(operator_session.token)
                return JSONResponse(
                    {"detail": "TEST_VISUAL_ACCESS_EXPIRED"}, status_code=401
                )
            # A TEST credential (operator or guest) must never impersonate any
            # privileged or identity-claimed Global ID, including public 0000000088.
            async with db_session() as db:
                safe_target = await is_safe_synthetic_account(db, operator_session.global_id)
            if not safe_target:
                SESSIONS.revoke(operator_session.token)
                return JSONResponse({"detail": "DEMO_SESSION_OWNER_PROTECTED"}, status_code=403)
            # All Genesis synthetic scopes are bound to the current durable
            # TEST lease, not merely the Global ID. An old bearer cannot
            # write after logout, expiry or assignment to another visitor.
            if CONFIG.genesis_mode and operator_session.scope in {"guest","visual","operator"}:
                if not operator_session.lease_hash:
                    return JSONResponse({"detail":"GUEST_LEASE_REQUIRED"},status_code=401)
                async with db_session() as db:
                    lease_matches = await test_admin_lease_active(
                        db, operator_session.global_id,
                        operator_session.lease_hash,
                        allow_reserved_quarantine=(
                            CONFIG.genesis_mode
                            and operator_session.scope in {"guest", "operator"}
                            and operator_session.global_id in CONFIG.admin_global_ids
                        ),
                    )
                if not lease_matches:
                    SESSIONS.revoke(operator_session.token)
                    return JSONResponse({"detail":"GUEST_LEASE_EXPIRED_OR_REVOKED"},
                                        status_code=401)
            visual_aggregate = (
                operator_session.scope == "visual"
                and CONFIG.visual_access_active
                and visual_admin_report_allowed(path, method)
            )
            env_admin_approved = (
                CONFIG.genesis_mode
                and operator_session.scope in {"guest", "operator"}
                and operator_session.global_id in CONFIG.admin_global_ids
                and bool(operator_session.lease_hash)
            )
            if (path == "/api/admin" or path.startswith("/api/admin/")) and not env_admin_approved:
                return JSONResponse({"detail": "TEST_ADMIN_GLOBAL_ID_NOT_ALLOWED"}, status_code=403)
            # An authenticated Genesis guest may request a TON proof and
            # submit it to the unchanged cryptographic backend, never as
            # verified Telegram identity. The exact leased Global ID was
            # checked above. Mutating wallet routes also require TEST CSRF.
            guest_ton_route = (
                genesis_guest_wallet_route(method, path)
                if CONFIG.genesis_mode and operator_session.scope == "guest"
                else None
            )
            guest_write = (
                guest_ton_route == "write" or (
                operator_session.scope=="guest" and method=="POST"
                and (path in {
                    "/api/panels/activate",
                    "/api/exchange/convert",
                    "/api/staging/guest-topup",
                    # Exact authenticated activity trigger; server controls bank writes.
                    "/api/deposit/direct-check",
                } or (path=="/api/sync/me" and
                      request.query_params.get("fresh")=="1"))
                )
            )
            if operator_session.scope in {"guest", "visual"} and not env_admin_approved:
                safe_get_prefixes = (
                    "/api/me", "/api/panels", "/api/ranks", "/api/referrals",
                    "/api/tasks", "/api/hub", "/api/shop", "/api/shopfront",
                    "/api/profile", "/api/skins", "/api/ads", "/api/nft",
                    "/api/exchange", "/api/wallets/me",
                )
                safe_get = method in {"GET", "HEAD"} and (
                    path in {"/api/auth/session", "/api/staging/session"}
                    or guest_ton_route == "read"
                    # Deposit metadata remains GET-only; the exact direct-check
                    # POST is a separately CSRF-guarded shared watcher trigger.
                    or (operator_session.scope == "guest" and path == "/api/deposit/direct-open")
                    # The authenticated TEST guest may read only their own
                    # panel count and withdrawal history through existing owner-scoped routes.
                    or (operator_session.scope == "guest" and path in {
                        "/api/user/me/panels-summary", "/api/withdraw/list",
                    })
                    or any(path == base or path.startswith(base + "/") for base in safe_get_prefixes)
                    or visual_aggregate
                )
                # Fresh=0 bypasses energy-generation writes in canonical sync.
                # No other POST/PUT/PATCH/DELETE is permitted for public preview.
                safe_sync = method == "POST" and path == "/api/sync/me" and request.query_params.get("fresh") == "0"
                safe_logout = method == "POST" and path in {"/api/auth/logout", "/api/staging/logout"}
                if not (safe_get or safe_sync or safe_logout or guest_write):
                    return JSONResponse({"detail": "DEMO_GUEST_READ_ONLY"}, status_code=403)
                if guest_write:
                    supplied=request.headers.get("X-EFHC-Test-CSRF","")
                    if not supplied or not secrets.compare_digest(
                        supplied,operator_session.csrf
                    ):
                        return JSONResponse({"detail":"DEMO_CSRF_REQUIRED"},status_code=403)
        if path.startswith("/api/staging/"):
            # Native verified provider and public guest cannot use operator controls.
            allowed_staging = (
                operator_session is not None
                and (
                    operator_session.scope in {"operator"}
                    or (operator_session.scope in {"guest", "visual"}
                        and path in {"/api/staging/session", "/api/staging/logout", "/api/staging/guest-topup"}
                        and (path!="/api/staging/guest-topup" or
                             operator_session.scope=="guest"))
                )
            )
            if not allowed_staging:
                return JSONResponse({"detail": "DEMO_OPERATOR_SESSION_REQUIRED"}, status_code=401)
        elif operator_session is None:
            if not header_token:
                return JSONResponse({"detail": "DEMO_SESSION_REQUIRED"}, status_code=401)
            try:
                await authenticate_native_session(header_token)
            except (AuthSessionNotActive, InvalidAuthRuntimeInput, ValueError):
                return JSONResponse({"detail": "DEMO_NATIVE_SESSION_INVALID"}, status_code=401)
        if operator_session is not None and (operator_session.scope == "operator" or env_admin_approved):
            # CSRF applies to browser-cookie operator commands; the operator
            # console sends this header for all writes regardless of bearer.
            # A non-fresh snapshot is a read operation carried by POST.
            # Permit the live Pages smoke and browser initial load without
            # exempting actual writes or fresh=1 generation from CSRF.
            nonmutating_sync = (
                method == "POST"
                and path == "/api/sync/me"
                and request.query_params.get("fresh") == "0"
            )
            if method not in {"GET", "HEAD"} and not nonmutating_sync and not header_token:
                received = request.headers.get("X-EFHC-Test-CSRF", "")
                if not received or not secrets.compare_digest(received, operator_session.csrf):
                    return JSONResponse({"detail": "DEMO_CSRF_REQUIRED"}, status_code=403)
            # The production deps expect a Bearer token even when the test
            # operator authenticated through a HttpOnly cookie.
            request.scope["headers"] = [
                (k, v) for k, v in request.scope["headers"]
                if k.lower() != b"authorization"
            ] + [(b"authorization", f"Bearer {token}".encode("ascii"))]
    # Full TEST Admin authority is request-local, never inferred from a
    # client-provided Global ID alone. All prior lease/RBAC guards apply.
    with (authorized_test_admin(int(operator_session.global_id))
          if env_admin_approved else nullcontext()):
        response = await call_next(request)
    if path.startswith("/api/"):
        response.headers["X-EFHC-Data-Source"] = "neon-test"
        response.headers["Cache-Control"] = "no-store"
    return response

# The original FastAPI CORS list lacks the TEST CSRF header. This additional
# outer middleware allows only exact origins and only the TEST header set.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CONFIG.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key",
                   "X-Request-ID", "X-EFHC-Test-CSRF", "X-EFHC-Handoff",
                   "X-Telegram-Init-Data", "X-Event-Id", "X-Delivery-Id",
                   "X-Telegram-Bot-Api-Secret-Token"],
    expose_headers=["X-EFHC-Data-Source", "Content-Disposition", "X-Request-ID"],
)

_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _demo_lifespan(app_instance):
    # Fail before serving if the expected physical Neon schema or initial
    # test account is missing. Never create tables or auto-migrate here.
    async with db_session() as db:
        inventory = await inspect_schema(
            db, require_demo_views=not CONFIG.genesis_mode
        )
        if not inventory["ok"]:
            raise RuntimeError("NEON_TEST_SCHEMA_MISSING: " + ", ".join(inventory["missing"]))
        if CONFIG.genesis_mode:
            # No DDL, no compatibility fabrication, no privileged account seed.
            # Verify the exact completed Genesis before accepting a request.
            await assert_completed_genesis(db)
            if not await is_safe_synthetic_account(db, CONFIG.public_global_id):
                raise RuntimeError("GENESIS_PUBLIC_TEST_ACCOUNT_UNSAFE")
        if not await check_user(db, CONFIG.initial_global_id):
            raise RuntimeError("DEMO_INITIAL_GLOBAL_ID does not exist in Neon TEST")
    log.info("EFHC DEMO Neon verified: physical=%d, views=%d",
             inventory["physical_tables"], inventory["views"])
    # Only presence/flags are logged. Never log BotFather tokens or signed initData.
    provider_settings = get_settings()
    log.info("EFHC DEMO authentication readiness: telegram_bot_configured=%s; telegram_provider_enabled=%s; ton_provider_enabled=%s",
             bool(getattr(provider_settings, "BOT_TOKEN", "")),
             bool(getattr(provider_settings, "AUTH_PROVIDER_FLAGS", {}).get("telegram")),
             bool(getattr(provider_settings, "AUTH_PROVIDER_FLAGS", {}).get("ton")))
    async with _original_lifespan(app_instance):
        stop = asyncio.Event()
        task = (asyncio.create_task(periodic_energy(stop, CONFIG.scheduler_period))
                if CONFIG.scheduler_enabled else None)
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                await task


app.router.lifespan_context = _demo_lifespan
app.title = "EFHC DEMO backend — Neon TEST, genuine EFHC business API"
