"""Explicit, fail-closed configuration of an isolated EFHC demo API process."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, parse_qsl, urlencode, urlunsplit


# Neon TEST is restricted to the exact existing TEST branch endpoint.
# This is independent of DEMO_NEON_HOST (which is operator-supplied).
_NEON_TEST_HOST = "ep-fragrant-feather-zaribpm5.c-2.eu-west-2.aws.neon.tech"
_NEON_TEST_POOLER_HOST = _NEON_TEST_HOST.replace(".c-2.", "-pooler.c-2.")
_ALLOWED_NEON_TEST_HOSTS = frozenset({_NEON_TEST_HOST, _NEON_TEST_POOLER_HOST})
# Dedicated completed Genesis TEST project (never an alternative production host).
_GENESIS_TEST_HOST = "ep-weathered-heart-zak4zgp6.c-2.eu-west-2.aws.neon.tech"
_GENESIS_TEST_POOLER_HOST = _GENESIS_TEST_HOST.replace(".c-2.", "-pooler.c-2.")
_ALLOWED_GENESIS_TEST_HOSTS = frozenset({
    _GENESIS_TEST_HOST, _GENESIS_TEST_POOLER_HOST,
})


class DemoConfigurationError(RuntimeError):
    pass


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_test_admin_ids(raw: str) -> frozenset[str]:
    """Only exact ten-digit IDs from the pinned Genesis synthetic guest pool."""
    if not raw.strip():
        return frozenset()
    items = [part.strip() for part in raw.split(",")]
    if any(len(v) != 10 or not v.isascii() or not v.isdigit()
           or not 3001 <= int(v) <= 4000 for v in items):
        raise DemoConfigurationError("EFHC_TEST_ADMIN_GLOBAL_IDS_INVALID")
    if len(items) != len(set(items)):
        raise DemoConfigurationError("EFHC_TEST_ADMIN_GLOBAL_IDS_DUPLICATED")
    return frozenset(items)


# OWNER-controlled, non-secret TEST Admin allowlist committed in private GitHub.
# The same source is included by the DEMO Docker build and the backend source tree.
def backend_root() -> Path:
    package = Path(__file__).resolve().parent
    # Source checkout and existing isolated container projection use different paths.
    if package.parent.name == "test" and package.parent.parent.name == "environments":
        return package.parents[2] / "backend"
    return package.parent / "backend"


_ADMIN_GLOBAL_IDS_FILE = backend_root() / ".env.admin-global-ids"


def read_repo_test_admin_ids(path: Path = _ADMIN_GLOBAL_IDS_FILE) -> frozenset[str]:
    """Read the one canonical private-repository ENV assignment, fail closed."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DemoConfigurationError("EFHC_TEST_ADMIN_GLOBAL_IDS_FILE_UNAVAILABLE") from exc
    entries = [
        line.strip() for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    prefix = "EFHC_TEST_ADMIN_GLOBAL_IDS="
    if len(entries) != 1 or not entries[0].startswith(prefix):
        raise DemoConfigurationError("EFHC_TEST_ADMIN_GLOBAL_IDS_FILE_INVALID")
    return parse_test_admin_ids(entries[0][len(prefix):])


@dataclass(frozen=True)
class DemoConfig:
    database_url: str
    neon_host: str
    password: str
    initial_global_id: str
    cors_origins: tuple[str, ...]
    cookie_secure: bool
    cookie_name: str
    scheduler_enabled: bool
    scheduler_period: int
    max_topup_efhc: str
    public_global_id: str = "0000001000"  # synthetic, non-admin TEST fixture only
    dataset: str = "legacy"
    testnet_integrations_enabled: bool = False
    admin_global_ids: frozenset[str] = field(default_factory=frozenset)
    visual_access_key: str = field(default="", repr=False)
    visual_access_until: datetime | None = None

    @property
    def visual_access_active(self) -> bool:
        return bool(self.visual_access_key and self.visual_access_until is not None
                    and datetime.now(UTC) < self.visual_access_until)

    @property
    def genesis_mode(self) -> bool:
        return self.dataset == "genesis"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "DemoConfig":
        env = os.environ if environ is None else environ
        if not _env_bool(env.get("EFHC_DEMO_ENABLED", "")):
            raise DemoConfigurationError("EFHC_DEMO_ENABLED=1 is required")
        if env.get("ENV", "").lower() in {"prod", "production", "stage", "staging"}:
            raise DemoConfigurationError("DEMO cannot run in production/staging runtime ENV")
        if _env_bool(env.get("ALLOW_REAL_FUNDS", "")):
            raise DemoConfigurationError("ALLOW_REAL_FUNDS must be disabled")
        url = env.get("DEMO_DATABASE_URL", "").strip()
        expected_host = env.get("DEMO_NEON_HOST", "").strip().lower()
        dataset = env.get("DEMO_DATASET", "legacy").strip().lower()
        if dataset not in {"legacy", "genesis"}:
            raise DemoConfigurationError("DEMO_DATASET must be legacy or genesis")
        # In real Genesis runtime, GitHub's tracked ENV file is authoritative.
        # Explicit injected environ retains legacy/unit-test configuration behavior.
        admin_global_ids = (
            read_repo_test_admin_ids() if dataset == "genesis" and environ is None
            else parse_test_admin_ids(env.get("EFHC_TEST_ADMIN_GLOBAL_IDS", ""))
        )
        if admin_global_ids and dataset != "genesis":
            raise DemoConfigurationError("TEST Admin Global IDs require pinned Genesis TEST")
        testnet_enabled = _env_bool(env.get("EFHC_DEMO_REAL_TESTNET", ""))
        if testnet_enabled:
            from demo_backend.testnet_policy import (
                DemoTestnetPolicyError, verified_testnet_target,
            )
            try:
                verified_testnet_target(dict(env))
            except DemoTestnetPolicyError as exc:
                raise DemoConfigurationError(str(exc)) from exc
        allowed_hosts = (
            _ALLOWED_GENESIS_TEST_HOSTS if dataset == "genesis"
            else _ALLOWED_NEON_TEST_HOSTS
        )
        if not url:
            raise DemoConfigurationError(
                "DEMO_DATABASE_URL is not set or is empty in the running service"
            )
        parsed = urlsplit(url)
        if parsed.scheme not in {"postgresql", "postgresql+asyncpg", "postgres"}:
            raise DemoConfigurationError(
                "DEMO_DATABASE_URL has an unsupported URL scheme; use a PostgreSQL DSN without surrounding quotes"
            )
        if expected_host not in allowed_hosts or parsed.hostname != expected_host:
            raise DemoConfigurationError(
                "DEMO_NEON_HOST must match the pinned Neon TEST dataset endpoint"
            )
        if not parsed.username or not parsed.password or not parsed.path or parsed.path == "/":
            raise DemoConfigurationError("Neon TEST DSN lacks database or credentials")
        if not any(value.lower() == "require" for value in parse_qs(parsed.query).get("sslmode", [])):
            raise DemoConfigurationError("Neon TEST DSN requires sslmode=require")
        inherited_url = env.get("DATABASE_URL", "").strip()
        if inherited_url and inherited_url != url:
            raise DemoConfigurationError("A different DATABASE_URL is set: refuse cross-environment access")
        password = env.get("DEMO_OPERATOR_PASSWORD", "")
        if len(password) < 16 or password.lower() in {"changeme", "demo", "password", "1234567890123456"}:
            raise DemoConfigurationError("Set a distinct DEMO_OPERATOR_PASSWORD (>=16 characters)")
        initial = env.get("DEMO_INITIAL_GLOBAL_ID", "").strip()
        if len(initial) != 10 or not initial.isascii() or not initial.isdigit() or initial == "0000000000":
            raise DemoConfigurationError("DEMO_INITIAL_GLOBAL_ID must be a real 10-digit TEST account")
        if dataset == "genesis" and initial == "0000000088":
            raise DemoConfigurationError(
                "Genesis reserved SuperAdmin Global ID 88 must never be a TEST account"
            )
        raw_origins = env.get("DEMO_CORS_ORIGINS", "https://gly-efhc.github.io").strip()
        origins = tuple(sorted(set(v.strip() for v in raw_origins.split(",") if v.strip())))
        if not origins or any(v == "*" or (not v.startswith("https://") and not v.startswith("http://localhost:") and not v.startswith("http://127.0.0.1:")) for v in origins):
            raise DemoConfigurationError("DEMO_CORS_ORIGINS must list exact HTTPS/localhost origins")
        period = int(env.get("DEMO_ENERGY_PERIOD_SECONDS", "60"))
        if period < 10 or period > 3600:
            raise DemoConfigurationError("Energy scheduler period must be 10..3600 seconds")
        from decimal import Decimal, InvalidOperation
        max_topup = env.get("DEMO_MAX_TOPUP_EFHC", "10000.00000000")
        try:
            dec = Decimal(max_topup)
            if dec <= 0 or dec.as_tuple().exponent < -8:
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise DemoConfigurationError("DEMO_MAX_TOPUP_EFHC must be positive D8") from None
        # This is a short-lived TEST visual pass, never an Admin/RBAC credential.
        visual_key = env.get("EFHC_TEST_ADMIN_ACCESS_KEY", "")
        visual_until_raw = env.get("EFHC_TEST_ADMIN_ACCESS_EXPIRES_AT", "")
        visual_until = None
        if visual_key:
            if len(visual_key) < 40 or not visual_until_raw:
                raise DemoConfigurationError("TEST visual key and expiry are required")
            try:
                visual_until = datetime.fromisoformat(visual_until_raw.replace("Z", "+00:00"))
            except ValueError:
                raise DemoConfigurationError("Invalid ISO timestamp for visual key") from None
            if visual_until.tzinfo is None or visual_until.utcoffset() is None:
                raise DemoConfigurationError("Visual key expiry must specify UTC timezone")
            visual_until = visual_until.astimezone(UTC)
        public_global_id = env.get("DEMO_PUBLIC_GLOBAL_ID", "0000001000").strip()
        if len(public_global_id) != 10 or not public_global_id.isascii() or not public_global_id.isdigit() or public_global_id == "0000000000":
            raise DemoConfigurationError("DEMO_PUBLIC_GLOBAL_ID must be a 10-digit synthetic TEST account")
        if dataset == "genesis" and public_global_id == "0000000088":
            raise DemoConfigurationError(
                "Genesis public TEST account must not use reserved SuperAdmin Global ID 88"
            )
        return cls(database_url=url, neon_host=expected_host, password=password,
            initial_global_id=initial, cors_origins=origins,
            cookie_secure=_env_bool(env.get("DEMO_COOKIE_SECURE", "1")),
            cookie_name="efhc_demo_sid",
            scheduler_enabled=_env_bool(env.get("DEMO_ENERGY_SCHEDULER", "0")),
            scheduler_period=period,
            max_topup_efhc=max_topup, public_global_id=public_global_id,
            dataset=dataset, testnet_integrations_enabled=testnet_enabled,
            admin_global_ids=admin_global_ids,
            visual_access_key=visual_key,
            visual_access_until=visual_until)


def prepare_backend_environment(config: DemoConfig) -> None:
    """Use Neon TEST and disable automatic funds sends; retain TON and ad APIs."""
    # Neon exports libpq-specific channel_binding=require; asyncpg does not
    # accept it as a connection keyword. Keep sslmode=require for the original
    # backend engine normalizer, which enforces TLS via connect_args["ssl"].
    if config.genesis_mode:
        # The canonical EFHC asyncpg adapter validates CA and DNS hostname
        # when channel_binding is present. Keep the full Neon TLS options.
        asyncpg_url = config.database_url
    else:
        # Preserve legacy TEST behavior until its independent migration.
        parts = urlsplit(config.database_url)
        query = urlencode([(key, value) for key, value in
                           parse_qsl(parts.query, keep_blank_values=True)
                           if key.lower() != "channel_binding"])
        asyncpg_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                 query, parts.fragment))
    os.environ.update({
        "ENV": "local", "DATABASE_URL": asyncpg_url,
        "ALLOW_REAL_FUNDS": "false", "RUN_EMBEDDED_TON_AGENT": "false",
        "ALLOW_INSECURE_USER_HEADERS": "false",
        "CORS_ALLOW_ORIGINS": ",".join(config.cors_origins),
    })
    # Keep guest-pool reservation and request-scoped Admin checks synchronized
    # with the very same GitHub-managed list (never the stale Render ENV value).
    if config.genesis_mode:
        os.environ["EFHC_TEST_ADMIN_GLOBAL_IDS"] = ",".join(sorted(config.admin_global_ids))
    # Actual proof verification and TON login must be testable. Provider
    # feature flag is isolated to this DEMO process; ENV can override it.
    # Enable Telegram signature verification exclusively in the DEMO process.
    # Never convert an unverified numeric ID into a session.
    import json
    try:
        flags = json.loads(os.environ.get("AUTH_PROVIDER_FLAGS", "{}"))
    except (ValueError, TypeError) as exc:
        raise DemoConfigurationError("AUTH_PROVIDER_FLAGS must be valid JSON") from exc
    if not isinstance(flags, dict):
        raise DemoConfigurationError("AUTH_PROVIDER_FLAGS must be a JSON object")
    flags.setdefault("ton", True)
    flags["telegram"] = True
    os.environ["AUTH_PROVIDER_FLAGS"] = json.dumps(flags, separators=(",", ":"))
    # Proof domain must match the Pages frontend (not the API hostname).
    frontend_origin = next((v for v in config.cors_origins
                            if v.startswith("https://") and "github.io" in v),
                           next((v for v in config.cors_origins if v.startswith("https://")), ""))
    if frontend_origin:
        os.environ.setdefault("APP_URL", frontend_origin)
        os.environ.setdefault("FRONTEND_URL", frontend_origin)
