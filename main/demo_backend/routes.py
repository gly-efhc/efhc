"""Operator-only DEMO control plane; does not create or migrate tables."""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from demo_backend.config import DemoConfig
from demo_backend.account_guards import is_safe_synthetic_account
from demo_backend.guest_pool import (
    GuestPoolConfigurationError, GuestPoolFull, allocate_guest, release_guest,
    _digest as hash_guest_resume_token,
)
from demo_backend.schema import check_user, inspect_schema
from demo_backend.session_store import DemoSession, DemoSessionStore


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)
    resume_token: str | None = Field(default=None, max_length=256)


class VisualAccessRequest(BaseModel):
    key: str = Field(min_length=1, max_length=256)
    resume_token: str | None = Field(default=None, max_length=256)


class GuestLeaseRequest(BaseModel):
    resume_token: str | None = Field(default=None, max_length=256)


class SelectGlobalIdRequest(BaseModel):
    global_id: str = Field(pattern=r"^[0-9]{10}$")


class DemoTopUpRequest(BaseModel):
    amount_efhc: str = Field(pattern=r"^\d+(?:\.\d{1,8})?$")


class DemoRoutes:
    def __init__(self, config: DemoConfig, sessions: DemoSessionStore):
        self.config = config
        self.sessions = sessions
        self.router = APIRouter(prefix="/api/staging", tags=["EFHC-DEMO-TEST-ONLY"])
        self._failures: dict[str, deque[float]] = {}
        self._guest_issues: dict[str, deque[float]] = {}
        self._register()

    def _dependency(self):
        from app.core.database_core import fastapi_db_dependency
        return fastapi_db_dependency

    def _current_session(self, request: Request) -> DemoSession:
        raw = request.headers.get("Authorization", "")
        raw_token = raw[7:] if raw.startswith("Bearer ") else ""
        cookie_token = request.cookies.get(self.config.cookie_name, "")
        token = raw_token or cookie_token
        session = self.sessions.get(token)
        if session is None:
            raise HTTPException(status_code=401, detail="DEMO_SESSION_REQUIRED")
        return session

    def _write_session_cookie(self, response: Response, session: DemoSession) -> None:
        response.set_cookie(
            key=self.config.cookie_name, value=session.token,
            httponly=True, secure=self.config.cookie_secure,
            samesite="none" if self.config.cookie_secure else "lax",
            max_age=8 * 3600, path="/",
        )
        response.headers["Cache-Control"] = "no-store"

    def _require_csrf(self, request: Request, session: DemoSession) -> None:
        candidate = request.headers.get("X-EFHC-Test-CSRF", "")
        if not candidate or not secrets.compare_digest(candidate, session.csrf):
            raise HTTPException(status_code=403, detail="DEMO_CSRF_REQUIRED")

    def _register(self) -> None:
        get_db = self._dependency()
        router = self.router

        @router.post("/visual-access")
        async def visual_access(
            body: VisualAccessRequest, request: Request, response: Response,
            db: AsyncSession = Depends(get_db),
        ):
            """Temporary visual-only session: never an Admin principal."""
            ip = request.client.host if request.client else "unknown"
            attempts = self._failures.setdefault("visual:" + ip, deque())
            now = time.monotonic()
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 6:
                raise HTTPException(status_code=429, detail="TEST_VISUAL_RATE_LIMIT")
            if not self.config.visual_access_active or not secrets.compare_digest(
                body.key, self.config.visual_access_key
            ):
                attempts.append(now)
                raise HTTPException(status_code=401, detail="TEST_VISUAL_ACCESS_DENIED")
            lease = None
            issued = None
            if self.config.genesis_mode:
                try:
                    lease = await allocate_guest(db, resume_token=body.resume_token)
                    issued = self.sessions.issue(
                        lease.global_id, scope="visual",
                        lease_hash=hash_guest_resume_token(lease.resume_token),
                    )
                    await db.commit()
                except (GuestPoolFull, GuestPoolConfigurationError):
                    await db.rollback()
                    raise HTTPException(status_code=503, detail="GENESIS_GUEST_POOL_UNAVAILABLE") from None
                except Exception:
                    await db.rollback()
                    if issued is not None:
                        self.sessions.revoke(issued.token)
                    raise
            else:
                if not await is_safe_synthetic_account(db, self.config.public_global_id):
                    raise HTTPException(status_code=503, detail="TEST_VISUAL_ACCOUNT_UNAVAILABLE")
                issued = self.sessions.issue(self.config.public_global_id, scope="visual")
            attempts.clear()
            self._write_session_cookie(response, issued)
            result = {
                "ok": True, "global_id": issued.global_id,
                "scope": "visual", "mode": "efhc-test-visual-readonly",
                "csrf": issued.csrf, "expires_at_epoch": int(issued.expires_at),
                "demo_bearer_token": issued.token,
            }
            if lease is not None:
                result["guest_resume_token"] = lease.resume_token
            return result

        @router.post("/login")
        async def login(body: LoginRequest, request: Request, response: Response,
                        db: AsyncSession = Depends(get_db)):
            ip = request.client.host if request.client else "unknown"
            attempts = self._failures.setdefault(ip, deque())
            now = time.monotonic()
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 6:
                raise HTTPException(status_code=429, detail="DEMO_LOGIN_RATE_LIMIT")
            if not secrets.compare_digest(body.password, self.config.password):
                attempts.append(now)
                raise HTTPException(status_code=401, detail="DEMO_BAD_CREDENTIALS")
            # Password alone never grants Admin or verified-provider ownership.
            lease = None
            issued = None
            if self.config.genesis_mode:
                try:
                    lease = await allocate_guest(db, resume_token=body.resume_token)
                    issued = self.sessions.issue(
                        lease.global_id, scope="operator",
                        lease_hash=hash_guest_resume_token(lease.resume_token),
                    )
                    await db.commit()
                except (GuestPoolFull, GuestPoolConfigurationError):
                    await db.rollback()
                    raise HTTPException(status_code=503, detail="GENESIS_GUEST_POOL_UNAVAILABLE") from None
                except Exception:
                    await db.rollback()
                    if issued is not None:
                        self.sessions.revoke(issued.token)
                    raise
            else:
                if not await is_safe_synthetic_account(db, self.config.public_global_id):
                    raise HTTPException(status_code=503, detail="DEMO_SYNTHETIC_ACCOUNT_UNAVAILABLE")
                issued = self.sessions.issue(self.config.public_global_id, scope="operator")
            attempts.clear()
            self._write_session_cookie(response, issued)
            result = {"ok": True, "global_id": issued.global_id, "csrf": issued.csrf,
                      "scope": "operator", "mode": "neon-test",
                      "expires_at_epoch": int(issued.expires_at),
                      "demo_bearer_token": issued.token}
            if lease is not None:
                result["guest_resume_token"] = lease.resume_token
            return result

        @router.post("/guest")
        async def guest(
            request: Request, body: GuestLeaseRequest | None = None,
            db: AsyncSession = Depends(get_db),
        ):
            """Issue an isolated 48-hour Genesis TEST guest lease, not ID 1000."""
            if not self.config.genesis_mode:
                raise HTTPException(status_code=503, detail="GENESIS_GUEST_ONLY")
            ip = request.client.host if request.client else "unknown"
            attempts = self._guest_issues.setdefault(ip, deque())
            now = time.monotonic()
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 30:
                raise HTTPException(status_code=429, detail="DEMO_GUEST_RATE_LIMIT")
            active_session = None
            try:
                lease = await allocate_guest(
                    db, resume_token=body.resume_token if body else None
                )
                active_session = self.sessions.issue(
                    lease.global_id, scope="guest",
                    lease_hash=hash_guest_resume_token(lease.resume_token),
                )
                await db.commit()
            except GuestPoolFull:
                await db.rollback()
                raise HTTPException(status_code=503, detail="GENESIS_GUEST_POOL_FULL") from None
            except GuestPoolConfigurationError:
                await db.rollback()
                raise HTTPException(status_code=503, detail="GENESIS_GUEST_POOL_UNAVAILABLE") from None
            except Exception:
                await db.rollback()
                if active_session is not None:
                    self.sessions.revoke(active_session.token)
                raise
            attempts.append(now)
            return {
                "ok": True, "global_id": active_session.global_id,
                "csrf": active_session.csrf, "scope": "guest",
                "mode": "genesis-test-guest",
                "expires_at_epoch": int(active_session.expires_at),
                "demo_bearer_token": active_session.token,
                "guest_resume_token": lease.resume_token,
                "guest_lease_expires_at": lease.expires_at.isoformat(),
            }

        @router.get("/session")
        async def session(request: Request, response: Response):
            s = self._current_session(request)
            response.headers["Cache-Control"] = "no-store"
            return {"ok": True, "global_id": s.global_id, "csrf": s.csrf,
                    "mode": "neon-test", "expires_at_epoch": int(s.expires_at)}

        @router.post("/select-global-id")
        async def select_global_id(body: SelectGlobalIdRequest, request: Request,
                                   response: Response, db: AsyncSession = Depends(get_db)):
            old = self._current_session(request)
            if old.scope != "operator":
                raise HTTPException(status_code=403, detail="DEMO_OPERATOR_REQUIRED")
            if self.config.genesis_mode:
                raise HTTPException(status_code=403, detail="GENESIS_GUEST_POOL_OWNER_IMMUTABLE")
            self._require_csrf(request, old)
            # Explicitly deny every admin and all claimed/verified identities,
            # including public SuperAdmin Global ID 0000000088.
            if not await is_safe_synthetic_account(db, body.global_id):
                raise HTTPException(status_code=403, detail="DEMO_ACCOUNT_SWITCH_FORBIDDEN")
            fresh = self.sessions.replace(old.token, body.global_id)
            if fresh is None:
                raise HTTPException(status_code=401, detail="DEMO_SESSION_EXPIRED")
            self._write_session_cookie(response, fresh)
            return {"ok": True, "global_id": fresh.global_id, "csrf": fresh.csrf,
                    "mode": "neon-test", "expires_at_epoch": int(fresh.expires_at), "demo_bearer_token": fresh.token}

        @router.post("/logout")
        async def logout(
            request: Request, response: Response,
            body: GuestLeaseRequest | None = None,
            db: AsyncSession = Depends(get_db),
        ):
            s = self._current_session(request)
            self._require_csrf(request, s)
            if s.scope in {"guest", "operator", "visual"} and self.config.genesis_mode:
                # Release only the matching browser token, never another slot.
                token = body.resume_token if body else None
                if (not token or hash_guest_resume_token(token)!=s.lease_hash):
                    raise HTTPException(status_code=403, detail="GUEST_LEASE_TOKEN_MISMATCH")
                released = await release_guest(
                    db, global_id=s.global_id, resume_token=token,
                )
                if not released:
                    await db.rollback()
                    raise HTTPException(status_code=409, detail="TEST_GUEST_RESET_UNSAFE")
                await db.commit()
            self.sessions.revoke(s.token)
            response.delete_cookie(self.config.cookie_name, path="/",
                                   secure=self.config.cookie_secure,
                                   samesite="none" if self.config.cookie_secure else "lax")
            response.headers["Cache-Control"] = "no-store"
            return {"ok": True}

        @router.get("/schema")
        async def schema(request: Request, db: AsyncSession = Depends(get_db)):
            self._current_session(request)
            return await inspect_schema(db, require_demo_views=not self.config.genesis_mode)

        @router.get("/routes")
        async def routes(request: Request):
            self._current_session(request)
            from fastapi.routing import APIRoute
            items = []
            for r in request.app.routes:
                if isinstance(r, APIRoute):
                    items.append({"path": r.path, "methods": sorted(r.methods or [])})
            return {"ok": True, "count": len(items), "routes": items}

        @router.get("/health")
        async def health(db: AsyncSession = Depends(get_db)):
            from sqlalchemy import text
            from sqlalchemy.exc import SQLAlchemyError
            try:
                ok = (await db.execute(text("SELECT 1"))).scalar_one_or_none() == 1
            except SQLAlchemyError:
                raise HTTPException(status_code=503, detail="NEON_TEST_UNAVAILABLE") from None
            return {"ok": ok, "mode": "neon-test", "database": "connected" if ok else "unavailable"}

        @router.get("/bank-snapshot")
        async def bank_snapshot(request: Request, db: AsyncSession = Depends(get_db)):
            self._current_session(request)
            from app.services.bank_metrics_snapshot_service import (
                refresh_bank_metrics_snapshot, snapshot_to_facts,
            )
            try:
                snapshot = await refresh_bank_metrics_snapshot(db)
                facts = snapshot_to_facts(snapshot)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            return {"ok": True, "source": "efhc_core.bank_metrics_snapshot",
                    "facts": facts}

        @router.post("/guest-topup")
        async def guest_topup(
            body: DemoTopUpRequest, request: Request,
            idem_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
            db: AsyncSession = Depends(get_db),
        ):
            """Owner-initiated, BANK-backed TEST credit (no actual deposit)."""
            s=self._current_session(request)
            if not self.config.genesis_mode or s.scope!="guest":
                raise HTTPException(status_code=403,detail="GENESIS_GUEST_ONLY")
            if not s.lease_hash:
                raise HTTPException(status_code=401,detail="GUEST_LEASE_REQUIRED")
            self._require_csrf(request,s)
            if not idem_key or not (8<=len(idem_key)<=128):
                raise HTTPException(status_code=400,detail="IDEMPOTENCY_KEY_REQUIRED")
            amount=Decimal(body.amount_efhc)
            if amount<=0 or amount>Decimal(self.config.max_topup_efhc):
                raise HTTPException(status_code=422,detail="TEST_TOPUP_AMOUNT_OUT_OF_RANGE")
            ok=(await db.execute(text("""
                SELECT EXISTS(
                  SELECT 1 FROM efhc_test.guest_leases l
                  JOIN efhc_test.guest_starter_baselines b
                    ON b.global_id=l.global_id
                  WHERE l.global_id=:gid AND l.token_hash=:digest
                  AND l.expires_at>now() AND
                  NOT EXISTS(SELECT 1 FROM efhc_test.guest_slot_quarantine q
                             WHERE q.global_id=l.global_id)
                )
            """),{"gid":int(s.global_id),"digest":s.lease_hash})).scalar_one()
            if not ok:
                await db.rollback()
                raise HTTPException(status_code=403,detail="TEST_GUEST_LEASE_NOT_ACTIVE")
            from app.services.transactions_service import (
                IdempotencyPayloadConflictError,credit_user_from_bank_nocommit,
            )
            ik=hashlib.sha256((
                "guest-topup:" +s.global_id+":"+s.lease_hash+":"+idem_key
            ).encode("ascii")).hexdigest()
            try:
                result=await credit_user_from_bank_nocommit(
                    db,global_id=int(s.global_id),amount=amount,
                    reason="demo_simulated_external_deposit",
                    idempotency_key=ik,
                    meta={"test_only":True,"real_funds":False,
                          "source":"genesis_guest_self_topup"},
                )
                await db.commit()
            except IdempotencyPayloadConflictError:
                await db.rollback()
                raise HTTPException(status_code=409,detail="TEST_TOPUP_IDEMPOTENCY_CONFLICT") from None
            except Exception:
                await db.rollback()
                raise
            return {
                "ok":True,"global_id":s.global_id,
                "amount_efhc":str(amount.quantize(Decimal("0.00000001"))),
                "main_balance":str(result.user__main__balance),
                "bank_balance":str(result.bank__main__balance),
                "reused":result.detail=="idempotent",
                "real_funds":False,"network":"genesis-test-only",
            }

        @router.post("/topup")
        async def topup(body: DemoTopUpRequest, request: Request,
                        idem_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
                        db: AsyncSession = Depends(get_db)):
            """Test bank transfer through exact production ledger, never a fake chain receipt."""
            s = self._current_session(request)
            if s.scope not in {"operator", "preview"}:
                raise HTTPException(status_code=403, detail="DEMO_OPERATOR_REQUIRED")
            self._require_csrf(request, s)
            if not idem_key or not (8 <= len(idem_key) <= 128):
                raise HTTPException(status_code=400, detail="IDEMPOTENCY_KEY_REQUIRED")
            amount = Decimal(body.amount_efhc)
            if amount <= 0 or amount > Decimal(self.config.max_topup_efhc):
                raise HTTPException(status_code=422, detail="DEMO_TOPUP_AMOUNT_OUT_OF_RANGE")
            from app.services.admin.admin_rbac import RBAC, AdminAuthError
            from app.services.admin.admin_logging import AdminLogger
            from app.services.transactions_service import credit_user_from_bank_nocommit
            from app.services.transactions_service import IdempotencyPayloadConflictError
            actor = 88 if s.scope == "preview" else int(self.config.initial_global_id)
            try:
                admin = await RBAC.resolve_admin(db, actor)
            except AdminAuthError:
                raise HTTPException(status_code=409, detail="DEMO_OPERATOR_ADMIN_NOT_CONFIGURED_IN_NEON") from None
            hashed = hashlib.sha256(("efhc-demo-topup-v1:" + idem_key).encode()).hexdigest()
            try:
                result = await credit_user_from_bank_nocommit(db,
                    global_id=int(s.global_id), amount=amount,
                    reason="demo_simulated_external_deposit", idempotency_key=hashed,
                    meta={"simulation": True, "external_transfer": False, "source": "demo_backend"})
                if result.detail != "idempotent":
                    await AdminLogger.write(db, actor_global_id=actor, admin_id=admin.id,
                        action="DEMO_EXTERNAL_TOPUP", entity="users", entity_id=int(s.global_id),
                        details=f"DEMO amount={amount}; idk_sha256={hashed}", required=True)
                await db.commit()
            except IdempotencyPayloadConflictError:
                await db.rollback()
                raise HTTPException(status_code=409, detail="DEMO_IDEMPOTENCY_CONFLICT") from None
            except Exception:
                await db.rollback()
                raise
            return {"ok": True, "global_id": s.global_id, "amount_efhc": str(amount),
                    "main_balance": str(result.user__main__balance),
                    "bank_balance": str(result.bank__main__balance),
                    "reused": result.detail == "idempotent", "real_funds": False}

        @router.post("/energy/tick")
        async def energy_tick(request: Request):
            s = self._current_session(request)
            if s.scope not in {"operator", "preview"}:
                raise HTTPException(status_code=403, detail="DEMO_OPERATOR_REQUIRED")
            self._require_csrf(request, s)
            from app.scheduler.generate_energy import run_once
            return {"ok": True, "result": await run_once(), "real_funds": False}
