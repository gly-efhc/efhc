from __future__ import annotations
import pytest
from demo_backend.config import DemoConfig, DemoConfigurationError


@pytest.fixture
def env():
    return {
        "EFHC_DEMO_ENABLED": "1", "ENV": "local",
        "DEMO_DATABASE_URL": "postgresql+asyncpg://unit:secret@ep-fragrant-feather-zaribpm5.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require",
        "DEMO_NEON_HOST": "ep-fragrant-feather-zaribpm5.c-2.eu-west-2.aws.neon.tech",
        "DEMO_OPERATOR_PASSWORD": "this-is-a-test-only-password",
        "DEMO_INITIAL_GLOBAL_ID": "0000000002",
        "DEMO_CORS_ORIGINS": "https://gly-efhc.github.io",
    }


def test_accepts_only_explicit_demo_neon(env):
    assert DemoConfig.from_env(env).initial_global_id == "0000000002"


@pytest.mark.parametrize("key,value", [
    ("ENV", "prod"), ("ALLOW_REAL_FUNDS", "1"),
    ("DEMO_NEON_HOST", "ep-production.eu-central-1.aws.neon.tech"),
    ("DEMO_OPERATOR_PASSWORD", "password"),
    ("DEMO_INITIAL_GLOBAL_ID", "88"),
    ("DATABASE_URL", "postgresql://prod:secret@ep-prod.aws.neon.tech/neondb"),
    ("DEMO_CORS_ORIGINS", "*"),
])
def test_fails_closed(env, key, value):
    env[key] = value
    with pytest.raises(DemoConfigurationError):
        DemoConfig.from_env(env)


def test_matching_non_test_neon_endpoint_is_rejected(env):
    # A matching DSN and DEMO_NEON_HOST must NOT authorize another Neon branch.
    other = "ep-another.eu-central-1.aws.neon.tech"
    env["DEMO_DATABASE_URL"] = f"postgresql+asyncpg://unit:secret@{other}/neondb?sslmode=require"
    env["DEMO_NEON_HOST"] = other
    with pytest.raises(DemoConfigurationError, match="pinned Neon TEST"):
        DemoConfig.from_env(env)


def test_pinned_test_pooler_endpoint_is_allowed(env):
    pooler = "ep-fragrant-feather-zaribpm5-pooler.c-2.eu-west-2.aws.neon.tech"
    env["DEMO_DATABASE_URL"] = f"postgresql+asyncpg://unit:secret@{pooler}/neondb?sslmode=require"
    env["DEMO_NEON_HOST"] = pooler
    assert DemoConfig.from_env(env).neon_host == pooler


def test_disabled_by_default(env):
    env.pop("EFHC_DEMO_ENABLED")
    with pytest.raises(DemoConfigurationError):
        DemoConfig.from_env(env)

def test_asyncpg_neon_channel_binding_removed_preserving_tls_and_test_scope(env):
    import os
    from unittest.mock import patch
    from urllib.parse import parse_qs, urlsplit
    from demo_backend.config import prepare_backend_environment

    env["DEMO_DATABASE_URL"] += "&channel_binding=require&application_name=efhc_test"
    config = DemoConfig.from_env(env)
    with patch.dict(os.environ, {}, clear=True):
        prepare_backend_environment(config)
        forwarded = os.environ["DATABASE_URL"]
        query = parse_qs(urlsplit(forwarded).query)
        assert "channel_binding" not in query
        assert query["sslmode"] == ["require"]
        assert query["application_name"] == ["efhc_test"]
        assert os.environ["ALLOW_REAL_FUNDS"] == "false"
        assert os.environ["RUN_EMBEDDED_TON_AGENT"] == "false"
    assert "channel_binding=require" in config.database_url


def test_empty_neon_database_url_fails_explicitly(env):
    env["DEMO_DATABASE_URL"] = ""
    with pytest.raises(DemoConfigurationError, match="not set or is empty"):
        DemoConfig.from_env(env)
