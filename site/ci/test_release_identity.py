import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from release_identity import identity


class ReleaseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        self.export = Path(self.tmp.name) / 'out'
        self.export.mkdir()
        files = {
            'site/RELEASE.json': '{"schema":"efhc.release.identity","environment":"TEST"}',
            'site/frontend/package-lock.json': '{}',
            'main/backend/openapi/openapi.json': '{}',
            'main/backend/migrations/example.py': '',
            'main/demo_backend/asgi.py': '',
        }
        for category in ('locale', 'faq'):
            for lang in ('ru', 'en', 'uk', 'de', 'fr', 'es', 'it', 'tr',
                         'pl', 'da', 'hi', 'id', 'sw', 'pt', 'ko', 'ja'):
                relative = f'{category}/{lang}.json'
                content = json.dumps({'language': lang})
                files[f'site/frontend/public/{relative}'] = content
                built = self.export / relative
                built.parent.mkdir(parents=True, exist_ok=True)
                built.write_text(content)
        for name, content in files.items():
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'source')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        (self.export / 'pwa-build.json').write_text(json.dumps({'static_export': True, 'build_id': 'test-generation'}))
        (self.export / 'sw.js').write_bytes(b'test fixture')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args])

    def test_identity_uses_exact_source_and_built_worker(self):
        result = identity(self.root, self.export, self.commit)
        self.assertEqual(result['source_commit'], self.commit)
        self.assertEqual(result['frontend_tree'], self.git('rev-parse', 'HEAD:site/frontend').decode().strip())
        self.assertEqual(result['service_worker_sha256'], hashlib.sha256(b'test fixture').hexdigest())
        self.assertEqual(len(result['public_language_assets_sha256']), 32)
        self.assertFalse(result['backend_runtime_attested'])
        self.assertFalse(result['database_migrations_attested'])

    def test_exported_translation_drift_is_rejected(self):
        (self.export / 'locale/uk.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Exported asset differs from source'):
            identity(self.root, self.export, self.commit)

    def test_wrong_checkout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'expected commit'):
            identity(self.root, self.export, 'wrong')

    def test_dirty_source_is_rejected(self):
        (self.root / 'site/frontend/package-lock.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Tracked release sources'):
            identity(self.root, self.export, self.commit)

    def test_missing_worker_is_rejected(self):
        (self.export / 'sw.js').unlink()
        with self.assertRaises(FileNotFoundError):
            identity(self.root, self.export, self.commit)

    def test_incomplete_pwa_is_rejected(self):
        (self.export / 'pwa-build.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Serwist generation'):
            identity(self.root, self.export, self.commit)

    def test_checked_in_workflows_do_not_import_or_push_source(self):
        repo = Path(__file__).resolve().parents[2]
        workflows = repo / '.github/workflows'
        self.assertFalse((workflows / 'efhc-import.yml').exists())
        pages = (workflows / 'efhc-pages.yml').read_text()
        self.assertNotIn('git push', pages)
        self.assertNotIn('source_archive_sha256', pages)
        for name in ('efhc-pages.yml', 'efhc-parity.yml', 'shop-native.yml', 'tonconnect-owner-mainnet-wallet-ci.yml'):
            self.assertIn('npm run build', (workflows / name).read_text())
        package = json.loads((repo / 'site/frontend/package.json').read_text())
        self.assertEqual(package['scripts']['build'], 'npm run typecheck && next build --webpack')
