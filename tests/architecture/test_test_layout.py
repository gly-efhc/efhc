import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestLayout(unittest.TestCase):
    def test_development_tests_are_outside_runtime_source(self):
        misplaced = list((ROOT / 'frontend' / 'src').rglob('*.test.mjs'))
        misplaced += list((ROOT / 'tests').glob('test_*.py'))
        self.assertEqual(misplaced, [])
        for name in ('frontend', 'backend', 'integration', 'architecture'):
            self.assertTrue((ROOT / 'tests' / name).is_dir())

    def test_full_frontend_runner_covers_all_current_suite_groups(self):
        scripts = json.loads((ROOT / 'frontend' / 'package.json').read_text())['scripts']
        runner = scripts['test:all']
        for group in ('parity', 'regression', 'reconstruction'):
            self.assertIn(f'../tests/frontend/{group}/*.test.mjs', runner)
        self.assertIn('pwa-sites-index-redirect.mjs', runner)
        self.assertIn('npm run test:all', (ROOT / '.github/workflows/efhc-parity.yml').read_text())
