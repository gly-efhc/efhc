"""Regression checks of the shipped read handlers and PostgreSQL nullable filters."""
from __future__ import annotations
import ast
import os
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(os.environ.get('EFHC_BACKEND_ROOT', Path(__file__).resolve().parents[3] / 'backend'))
def source(name):
    if (ROOT / name).is_file(): return (ROOT / name).read_text()
    return (ROOT / 'app' / ('services/admin' if name == 'admin_bonus_service.py' else 'services' if name == 'tasks_service.py' else 'routes') / name).read_text()
def handler(filename, name, values):
    tree = ast.parse(source(filename))
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    fn.decorator_list = []
    fn.args.defaults = [ast.Constant(None) for _ in fn.args.defaults]
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), fn], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, filename, 'exec'), values)
    return values[name]

class ReadContracts(unittest.IsolatedAsyncioTestCase):
    async def test_unstarted_task_has_no_fabricated_lifetime_id(self):
        async def rows(*args, **kwargs):
            return [dict(id=None, task_id=42, status='not_started'),dict(id=77, task_id=43, status='approved')], None
        def item(**values):
            if values['id'] is not None and values['id'] <= 0: raise ValueError('invalid Lifetime ID')
            return SimpleNamespace(**values, model_dump=lambda: values)
        fn = handler('tasks_routes.py', '_build_user_tasks_page', {
            '_clamp_limit': lambda n:n, '_decode_after_id': lambda c:None,
            'list_user_tasks':rows, 'UserTaskItem':item,'UserTasksPage':lambda **kw:kw,
            '_read_bonus_efhc':lambda row:'0.00000000','make_etag':lambda value:'exact',
        })
        out=await fn(SimpleNamespace(headers={}),SimpleNamespace(global_id=88),None,50,None)
        self.assertIsNone(out['items'][0].id)
        self.assertEqual(out['items'][0].task_id,42)
        self.assertEqual(out['items'][1].id,77)

    async def test_read_service_preserves_absence_of_submission_id(self):
        tree=ast.parse(source('tasks_service.py'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='list_user_tasks')
        values=[n for n in ast.walk(fn) if isinstance(n,ast.Dict)]
        mapping=next(n for n in values if any(isinstance(k,ast.Constant) and k.value=='id' for k in n.keys))
        expr=next(v for k,v in zip(mapping.keys,mapping.values) if isinstance(k,ast.Constant) and k.value=='id')
        value=eval(compile(ast.Expression(expr),'tasks_service.py','eval'),{'row':SimpleNamespace(id=None)})
        self.assertIsNone(value,'not-started status is absence, never Lifetime ID zero')

    async def test_default_health_guard_still_denies_unauthorized_caller(self):
        async def denied(*args): raise PermissionError('denied')
        request=SimpleNamespace(headers={},app=SimpleNamespace(dependency_overrides={}))
        fn=handler('system_routes.py','_detailed_health_guard',{'require_admin_or_nft_or_key':denied})
        with self.assertRaises(PermissionError): await fn(request,None)

    async def test_health_uses_application_scoped_preview_override(self):
        async def denied(*args): raise PermissionError('production guard')
        calls=[]
        async def preview(*args): calls.append('verified TEST preview')
        request=SimpleNamespace(headers={},app=SimpleNamespace(dependency_overrides={denied:preview}))
        fn=handler('system_routes.py','_detailed_health_guard',{'require_admin_or_nft_or_key':denied})
        await fn(request,None)
        self.assertEqual(calls,['verified TEST preview'])

    async def test_metrics_token_guard_keeps_its_independent_authority(self):
        calls=[]
        request=SimpleNamespace(headers={'X-Metrics-Token':'TEST'},app=SimpleNamespace(dependency_overrides={}))
        fn=handler('system_routes.py','_detailed_health_guard',{'_metrics_token_guard':lambda token:calls.append(token)})
        await fn(request,None)
        self.assertEqual(calls,['TEST'])

@unittest.skipUnless(os.environ.get('EFHC_READ_SQL_TEST_DSN'),'ephemeral native PostgreSQL required')
class NullablePostgresFilters(unittest.IsolatedAsyncioTestCase):
    async def test_actual_nullable_sql_fragments_bind_none_and_typed_values(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        engine=create_async_engine(os.environ['EFHC_READ_SQL_TEST_DSN'])
        fragments=set()
        for name in ['admin_bonus_service.py','admin_routes.py']:
            tree=ast.parse(source(name))
            for node in ast.walk(tree):
                if isinstance(node,ast.Constant) and isinstance(node.value,str):
                    fragments.update(re.findall(r'(?:CAST\(:\w+ AS [A-Z ]+\)|:\w+) IS NULL',node.value))
        self.assertGreaterEqual(len(fragments),7)
        try:
            async with engine.connect() as db:
                for expr in sorted(fragments):
                    key=re.search(r':(\w+)',expr).group(1)
                    with self.subTest(parameter=key,expression=expr):
                        self.assertTrue((await db.execute(text('SELECT '+expr),{key:None})).scalar_one())
                        value=datetime(2026,11,6,tzinfo=timezone.utc) if key.startswith('date_') else 88 if key in ['gid','global_id','cursor_id'] else 'pending'
                        self.assertFalse((await db.execute(text('SELECT '+expr),{key:value})).scalar_one())
        finally: await engine.dispose()

if __name__=='__main__': unittest.main()
