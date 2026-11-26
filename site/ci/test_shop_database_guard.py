import unittest
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
