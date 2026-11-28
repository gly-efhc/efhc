"""Fail closed before any destructive integration fixture can touch a database."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def check_database_environment(env):
    keys = ('DATABASE_URL', 'ASYNC_DATABASE_URL', 'SYNC_DATABASE_URL', 'PSYCOPG_URL')
    database_paths = set()
    for key in keys:
        raw = env.get(key, '')
        url = urlsplit(raw)
        if (url.scheme not in ('postgresql', 'postgresql+asyncpg', 'postgresql+psycopg')
                or url.hostname not in ('127.0.0.1', '::1')
                or url.path not in ('/efhc_shop_ci', '/efhc_regression_ci') or url.query or url.fragment
                or url.port != 5432 or url.username != 'postgres'):
            raise ValueError(f'{key}: disposable loopback PostgreSQL required')
        database_paths.add(url.path)
    if len(database_paths) != 1:
        raise ValueError('All database aliases must target the same disposable database')
    if env.get('ENV') != 'ci' or env.get('PYTHON_DOTENV_DISABLED') != '1':
        raise ValueError('Explicit isolated CI environment required')


if __name__ == '__main__':
    check_database_environment(os.environ)
    root = Path(__file__).resolve().parents[2]
    tests = sorted((root / 'tests/backend').rglob('test_shop_prepayment*.py'))
    tests += [root / 'tests/integration/test_shop_prepayment_postgresql.py',
              root / 'tests/integration/test_shop_signed_lifecycle.py']
    assert tests
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q', *map(str, tests)], cwd=root))
