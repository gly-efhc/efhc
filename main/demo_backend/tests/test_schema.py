from __future__ import annotations
import asyncio
from demo_backend.schema import inspect_schema, check_user, REQUIRED_TABLES, REQUIRED_VIEWS


class Result:
    def __init__(self, entries):
        self._entries = entries
    def mappings(self):
        return self
    def all(self):
        return self._entries
    def scalar_one_or_none(self):
        return self._entries[0] if self._entries else None


class FakeDb:
    def __init__(self, entries):
        self.entries = entries
    async def execute(self, stmt, params=None):
        return Result(self.entries)


def test_reports_actual_existing_tables_without_ddl():
    entries = [{"table_schema": s,"table_name": n,"table_type":"BASE TABLE"}
               for s, names in REQUIRED_TABLES.items() for n in names]
    entries += [{"table_schema":"efhc_demo_public","table_name":v,"table_type":"VIEW"} for v in REQUIRED_VIEWS]
    obj = asyncio.run(inspect_schema(FakeDb(entries)))
    assert obj["ok"] and not obj["missing"]
    assert obj["physical_tables"] == len(entries) - len(REQUIRED_VIEWS)
    assert obj["views"] == len(REQUIRED_VIEWS)


def test_requires_real_existing_user_id():
    assert not asyncio.run(check_user(FakeDb([]), "88"))
    assert asyncio.run(check_user(FakeDb([1]), "0000000088"))
