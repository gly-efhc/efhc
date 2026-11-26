from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.routes.admin_users_routes import admin_users_resolve_provider
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, global_ids: list[int]) -> None:
        self._rows = [SimpleNamespace(global_id=value) for value in global_ids]

    def fetchall(self):
        return list(self._rows)


class _Db:
    def __init__(self, global_ids: list[int]) -> None:
        self.global_ids = global_ids
        self.sql = ""
        self.params = None

    async def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params
        return _Result(self.global_ids)


async def test_проверка_provider_resolver_возвращает_один_global_id() -> None:
    db = _Db([8000000006])

    result = await admin_users_resolve_provider(
        q="  provider-subject-6  ",
        ctx=object(),
        db=db,
    )

    assert result.global_id == "8000000006"
    assert db.params == {
        "subject": "provider-subject-6",
        "username": "provider-subject-6",
        "global_id_value": None,
    }
    assert "u.global_id = :global_id_value" in db.sql
    assert "LOWER(u.username) = LOWER(:username)" in db.sql
    assert "ui.provider_subject = :subject" in db.sql
    assert "wb.wallet_address = :subject" in db.sql
    assert "ui.status = 'active'" in db.sql
    assert "ui.is_verified = TRUE" in db.sql
    assert "wb.is_active = TRUE" in db.sql
    assert "wb.proof_verified = TRUE" in db.sql
    assert "LIKE" not in db.sql.upper()


async def test_проверка_provider_resolver_возвращает_404_для_unknown_identifier() -> None:
    db = _Db([])

    with pytest.raises(HTTPException) as excinfo:
        await admin_users_resolve_provider(
            q="unknown-provider-subject",
            ctx=object(),
            db=db,
        )

    assert excinfo.value.status_code == 404


async def test_проверка_provider_resolver_отклоняет_conflicting_owners() -> None:
    db = _Db([8000000006, 8000000007])

    with pytest.raises(HTTPException) as excinfo:
        await admin_users_resolve_provider(
            q="conflicting-provider-subject",
            ctx=object(),
            db=db,
        )

    assert excinfo.value.status_code == 409


async def test_проверка_provider_resolver_нормализует_global_id_и_username() -> None:
    gid_db = _Db([8000000006])
    await admin_users_resolve_provider(q="8000000006", ctx=object(), db=gid_db)
    assert gid_db.params["global_id_value"] == 8000000006
    assert gid_db.params["username"] == "8000000006"

    username_db = _Db([8000000007])
    await admin_users_resolve_provider(q="@user_0007", ctx=object(), db=username_db)
    assert username_db.params["global_id_value"] is None
    assert username_db.params["username"] == "user_0007"
