import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def identity(root: Path, export: Path, expected_commit: str) -> dict:
    def git(*args: str) -> bytes:
        return subprocess.check_output(['git', '-C', str(root), *args])

    commit = git('rev-parse', 'HEAD').decode().strip()
    if commit != expected_commit:
        raise ValueError('Release checkout differs from expected commit')
    if git('status', '--porcelain', '--untracked-files=no', '--', 'site', 'main', 'ROUTES.json', '.github/workflows'):
        raise ValueError('Tracked release sources differ from checkout')
    policy = json.loads(git('show', 'HEAD:site/RELEASE.json'))
    if policy['schema'] != 'efhc.release.identity' or policy['environment'] != 'TEST':
        raise ValueError('Invalid TEST release identity contract')
    pwa = json.loads((export / 'pwa-build.json').read_bytes())
    if pwa.get('static_export') is not True or not pwa.get('build_id'):
        raise ValueError('Compiled static Serwist generation required')
    return {
        'schema': policy['schema'],
        'environment': policy['environment'],
        'source_commit': commit,
        'frontend_tree': git('rev-parse', 'HEAD:site/frontend').decode().strip(),
        'backend_source_tree': git('rev-parse', 'HEAD:main/backend').decode().strip(),
        'test_adapter_tree': git('rev-parse', 'HEAD:main/demo_backend').decode().strip(),
        'migration_source_tree': git('rev-parse', 'HEAD:main/backend/migrations').decode().strip(),
        'openapi_sha256': hashlib.sha256(git('show', 'HEAD:main/backend/openapi/openapi.json')).hexdigest(),
        'frontend_lock_sha256': hashlib.sha256(git('show', 'HEAD:site/frontend/package-lock.json')).hexdigest(),
        'serwist_build_id': pwa['build_id'],
        'service_worker_sha256': hashlib.sha256((export / 'sw.js').read_bytes()).hexdigest(),
        'backend_runtime_attested': False,
        'database_migrations_attested': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--export', required=True, type=Path)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = identity(root, args.export, args.expected_commit)
    (args.export / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
