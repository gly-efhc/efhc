"""Execute the actual read handlers without database writes or network access."""
from __future__ import annotations
import ast
import asyncio
import os
import re
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(os.environ.get('EFHC_READ_CONTRACT_ROOT', Path(__file__).parent))

def handler(filename, name, values):
    tree = ast.parse((ROOT / filename).read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    fn.decorator_list = []
    fn.args.defaults = [ast.Constant(None) for _ in fn.args.defaults]
    fn.args.kw_defaults = [ast.Constant(None) if v is not None else None for v in fn.args.kw_defaults]
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), fn], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(ROOT / filename), 'exec'), values)
    return values[name]

def d8(value):
    return Decimal(value).quantize(Decimal('0.00000001'))

class DTO:
    @staticmethod
    def model_validate(payload):
        # The published React contract requires fixed notation, never 0E-8.
        fields = ['bonus_balance', 'referrals_bonus_total', 'unit_bonus_per_active',
                  'full_cycle_direct_bonus', 'full_cycle_level_bonus', 'full_cycle_total_bonus']
        for field in fields:
            if not re.fullmatch(r'^-?\d+(?:\.\d{1,8})?$', payload[field]):
                raise ValueError(f'invalid D8 wire field: {field}')
        return payload

@dataclass
class Summary:
    active_count: int
    total_generated_by_panels: Decimal
    nearest_expire_at: datetime | None

class ReadContracts(unittest.IsolatedAsyncioTestCase):
    async def test_panels_summary_accepts_real_service_dataclass(self):
        expiry = datetime(2027, 1, 1, tzinfo=timezone.utc)
        async def service(*args, **kwargs):
            return Summary(2, Decimal('9007199254740993.12345678'), expiry)
        fn = handler('user_routes.py', 'get_my_panels_summary', {
            'svc_panels_summary': service, 'PanelsSummaryOut': lambda **kw: kw, 'd8': d8,
        })
        out = await fn(None, SimpleNamespace(global_id='0000000088'))
        self.assertEqual(out['active_count'], 2)
        self.assertEqual(out['total_generated_by_panels'], '9007199254740993.12345678')
        self.assertEqual(out['nearest_expire_at'], expiry.isoformat())

    async def test_empty_panels_preserve_fixed_zero(self):
        async def service(*args, **kwargs):
            return Summary(0, Decimal('0E-8'), None)
        fn = handler('user_routes.py', 'get_my_panels_summary', {
            'svc_panels_summary': service, 'PanelsSummaryOut': lambda **kw: kw, 'd8': d8,
        })
        out = await fn(None, SimpleNamespace(global_id='0000000088'))
        self.assertEqual(out['total_generated_by_panels'], '0.00000000')
        self.assertIsNone(out['nearest_expire_at'])

    async def test_referrals_zero_matches_react_contract_and_etag(self):
        step = SimpleNamespace(level=0, required_active=0, level_bonus=Decimal(0),
            direct_bonus_total=Decimal(0), cumulative_level_bonus=Decimal(0), cumulative_total_reward=Decimal(0))
        stats = SimpleNamespace(bonus_balance=Decimal('1.10000000'), referrals_bonus_total=Decimal('0E-8'),
            total_referrals=0, active_referrals=0, inactive_referrals=0, level=0, current_level_min=0,
            next_level=1, next_level_min=1, refs_to_next=1, progress=0, unit_bonus_per_active=Decimal('.1'),
            max_active_for_unit_bonus=100, bonus_asset='EFHCb', full_cycle_direct_bonus=Decimal(0),
            full_cycle_level_bonus=Decimal(0), full_cycle_total_bonus=Decimal(0), level_steps=[step],
            referral_code='88', referral_link=None)
        async def service(*args, **kwargs): return stats
        fn = handler('referrals_routes.py', '_stats_response', {
            'get_referrals_page_stats_global': service, 'd8': d8, 'ReferralsStatsOut': DTO,
            '_build_etag': lambda payload: '"exact"', '_etag_matches': lambda given, expected: given == expected,
            '_not_modified': lambda etag: SimpleNamespace(status_code=304, headers={'ETag': etag}),
        })
        response = SimpleNamespace(headers={})
        args = dict(owner=SimpleNamespace(global_id='0000000088'), response=response, if_none_match=None, db=None)
        out = await fn(**args)
        self.assertEqual(out['referrals_bonus_total'], '0.00000000')
        self.assertEqual(out['bonus_balance'], '1.10000000')
        self.assertEqual(out['level_steps'][0]['level_bonus'], '0.00000000')
        self.assertEqual(response.headers['ETag'], '"exact"')
        args['if_none_match'] = '"exact"'
        self.assertEqual((await fn(**args)).status_code, 304)

def load_export_store():
    import importlib.util
    import sys
    name = "efhc_isolated_profile_history_download"
    spec = importlib.util.spec_from_file_location(
        name, ROOT.parent / "services" / "profile_history_download.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.ProfileExportDownloadStore


class ProfileExportDownloads(unittest.IsolatedAsyncioTestCase):
    async def test_private_download_grant_is_one_use_and_cleans_file(self):
        from tempfile import TemporaryDirectory
        ProfileExportDownloadStore = load_export_store()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.csv"
            path.write_bytes(b"amount\n100\n")
            store = ProfileExportDownloadStore()
            ticket = store.issue(path, "EFHC_all_2026-11-27.csv", "text/csv")
            self.assertEqual(len(ticket), 43)
            self.assertIsNone(store.lookup("A" * 43))
            self.assertEqual(store.lookup(ticket).size, 11)
            self.assertIsNotNone(store.lookup(ticket))
            self.assertEqual(store.redeem(ticket).path, path)
            self.assertIsNone(store.redeem(ticket))
            self.assertIsNone(store.lookup(ticket))
            store.release(ticket)
            self.assertFalse(path.exists())

    async def test_expired_download_and_pending_capacity(self):
        from tempfile import TemporaryDirectory
        ProfileExportDownloadStore = load_export_store()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.xlsx"
            path.write_bytes(b"test")
            other = Path(directory) / "other.csv"
            other.write_bytes(b"test")
            store = ProfileExportDownloadStore(ttl=0.01, max_entries=1)
            ticket = store.issue(path, "EFHC_all_2026-11-27.xlsx", "application/test")
            with self.assertRaises(ValueError):
                store.issue(other, "EFHC_all_2026-11-27.csv", "text/csv")
            await asyncio.sleep(0.04)
            self.assertIsNone(store.lookup(ticket))
            self.assertFalse(path.exists())
            self.assertTrue(other.exists())


if __name__ == '__main__': unittest.main()
