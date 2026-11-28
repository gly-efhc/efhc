import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/ci"))
from run_shop_native import check_database_environment

class DatabaseSafety(unittest.TestCase):
    def fixture(self):
        return dict.fromkeys(('DATABASE_URL','ASYNC_DATABASE_URL','SYNC_DATABASE_URL','PSYCOPG_URL'), 'postgresql://postgres:synthetic@127.0.0.1:5432/efhc_shop_ci') | {'ENV':'ci','PYTHON_DOTENV_DISABLED':'1'}

    def test_accepts_disposable_loopback(self):
        check_database_environment(self.fixture())

    def test_every_database_alias_is_checked(self):
        for key in ('DATABASE_URL','ASYNC_DATABASE_URL','SYNC_DATABASE_URL','PSYCOPG_URL'):
            for value in ('postgresql://postgres@shared.example/efhc_shop_ci', 'postgresql://postgres@127.0.0.1:5432/production', 'postgresql://postgres@127.0.0.1:5432/efhc_shop_ci?host=shared.example', ''):
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    check_database_environment(self.fixture() | {key:value})

    def test_accepts_dedicated_full_regression_database(self):
        env = self.fixture()
        env = {k: v.replace('/efhc_shop_ci', '/efhc_regression_ci') for k, v in env.items()}
        check_database_environment(env)

    def test_rejects_mixed_database_aliases(self):
        env = self.fixture()
        env['DATABASE_URL'] = env['DATABASE_URL'].replace('/efhc_shop_ci', '/efhc_regression_ci')
        with self.assertRaises(ValueError):
            check_database_environment(env)
