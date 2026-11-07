"""Reject missing, incomplete or unsafe compiled Next.js Pages artifacts."""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--directory', required=True)
    ap.add_argument('--base-path', required=True)
    args = ap.parse_args()
    root = Path(args.directory)
    index = root / 'index.html'
    if not index.is_file():
        raise ValueError('Next static export missing index.html')
    content = index.read_text(encoding='utf-8')
    if '__NEXT_DATA__' not in content and '/_next/' not in content:
        raise ValueError('index.html does not appear to be a Next.js build')
    static = root / '_next' / 'static'
    js = list(static.rglob('*.js')) if static.exists() else []
    css = list(static.rglob('*.css')) if static.exists() else []
    if not js or not css:
        raise ValueError('Next compiled JavaScript/CSS missing')
    base = args.base_path.rstrip('/')
    if base and base + '/_next/' not in content:
        raise ValueError('Next static asset basePath was not applied')
    if not (root / 'public-runtime-config.js').is_file():
        raise ValueError('Public runtime bootstrap file missing')
    worker = root / 'sw.js'
    manifest = root / 'manifest.webmanifest'
    pwa = root / 'pwa-build.json'
    if not all(path.is_file() for path in (worker, manifest, pwa)):
        raise ValueError('Missing PWA Service Worker, Manifest or build config')
    config = json.loads(pwa.read_text(encoding='utf-8'))
    if config.get('static_export') is not True or not config.get('precache'):
        raise ValueError('PWA full static export precache is not configured')
    expected = base.rstrip('/') + '/'
    missing = []
    for item in config['precache']:
        if not isinstance(item, str) or not item.startswith(expected) or '?' in item or '#' in item:
            raise ValueError('Unsafe or unscoped PWA resource')
        candidate = (root / item[len(expected):]).resolve()
        if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
            missing.append(item)
    if missing:
        raise ValueError(f'PWA resources absent: {missing[:5]}')
    if len([item for item in config['precache'] if item.endswith('.html')]) != pages:
        raise ValueError('PWA does not cover every static HTML page')
    if 'const EFHC_PWA_BUILD_CONFIG =' not in worker.read_text(encoding='utf-8'):
        raise ValueError('Service Worker missing pinned build configuration')
    deployed_manifest = json.loads(manifest.read_text(encoding='utf-8'))
    if deployed_manifest.get('scope') != expected:
        raise ValueError('PWA Manifest scope differs from Pages basePath')
    if (root / 'efhc-demo-safety.js').exists():
        raise ValueError('Obsolete browser DEMO bootstrap is forbidden')
    forbidden = [
        p for p in root.rglob('*')
        if p.is_file() and (
            p.suffix.lower() in {'.zip', '.log', '.pem', '.key', '.db', '.sqlite'}
            or p.name.startswith('.env')
        )
    ]
    if forbidden:
        raise ValueError(f'Forbidden published asset: {forbidden[0]}')
    pages = len(list(root.rglob('*.html')))
    print(f'EFHC_PAGES_EXPORT_PASS js={len(js)} css={len(css)} pages={pages}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print('EFHC_PAGES_EXPORT_FAIL: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
