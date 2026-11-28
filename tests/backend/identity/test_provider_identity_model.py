"""Причинные ORM tests таблицы ``user_identities``."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.identity_models import UserIdentity


def test_repr_не_раскрывает_provider_subject_или_metadata() -> None:
    identity = UserIdentity(
        global_id=42,
        provider="telegram",
        provider_tenant="default",
        provider_subject="secret-provider-subject",
        status="active",
        is_primary=True,
        is_verified=True,
        verified_at=datetime.now(UTC),
        provider_metadata={"token": "secret-token"},
    )
    rendered = repr(identity)
    assert "secret-provider-subject" not in rendered
    assert "secret-token" not in rendered
    assert "telegram" in rendered
    assert "global_id=42" not in rendered
    assert "42" not in rendered


def test_orm_defaults_не_создают_account_или_session_fields() -> None:
    table = UserIdentity.__table__
    names = set(table.c.keys())
    assert "user" not in names
    assert "session_id" not in names
    assert "tg_id" not in names
    assert "wallet_address" not in names
    assert "proof" not in names
    assert "token" not in names
    assert table.c.provider_tenant.server_default is not None
    assert table.c.status.server_default is not None
    assert table.c.metadata.server_default is not None
