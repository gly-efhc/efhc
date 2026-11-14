"""Normalize actual compiled public asset paths for the Pages repository subpath.

Only asset URLs are rewritten. Never change React routes, JSON fixtures or API calls.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

PATTERN = re.compile(
    r'(["\'`(=])/(assets|locale|faq/[A-Za-z0-9_-]+\.json|'
    r'audio|fonts|images|icons|skins|demo|favicon\.ico|manifest\.webmanifest)'
    r'(?=[/?#"\'`\s)])'
)



# All assets and HTML shells in the actual exported site are included. No
# backend endpoints, tokens, environment files or non-public data are embedded.
# Every exported HTML identifies its own build, including HTML-only changes.
# Strip the generated marker before digesting for deterministic repeated runs.
BUILD_META = re.compile(r'<meta name="efhc-build-id" content="[a-f0-9]{24}">')
PWA_SUFFIXES = {'.html', '.js', '.css', '.json', '.webmanifest', '.woff',
                '.woff2', '.png', '.jpeg', '.jpg', '.webp', '.avif', '.ico',
                '.svg', '.mp3'}


FINGERPRINTED_CSS = re.compile(r'\.[a-f0-9]{16}\.css$')


def fingerprint_public_stylesheets(root: Path) -> int:
    """Create content-addressed copies of public CSS for the export only.

    Next can reference public CSS from compiled JS as well as HTML. Rewrite
    those paths, never the original stylesheet names or authored styling.
    Repeating export normalization is deterministic.
    """
    mapping: dict[str, str] = {}
    for stylesheet in sorted(root.glob('*.css')):
        if FINGERPRINTED_CSS.search(stylesheet.name):
            continue
        raw = stylesheet.read_bytes()
        hashed_name = f'{stylesheet.stem}.{hashlib.sha256(raw).hexdigest()[:16]}.css'
        hashed = root / hashed_name
        if not hashed.is_file() or hashed.read_bytes() != raw:
            hashed.write_bytes(raw)
        mapping[stylesheet.name] = hashed_name

    for artifact in sorted(root.rglob('*')):
        if not artifact.is_file() or artifact.suffix not in {'.html', '.js'} or artifact.name == 'sw.js':
            continue
        original = artifact.read_text(encoding='utf-8')
        updated = original
        for old, new in mapping.items():
            updated = updated.replace('/' + old, '/' + new)
        if updated != original:
            artifact.write_text(updated, encoding='utf-8')
    return len(mapping)



def partition_pwa_resources(root: Path, base: str, included: list[str]) -> tuple[list[str], list[str]]:
    """Prepare a deterministic candidate shell for Workbox without changing the active SW.

    The minimum shell starts with the current landing HTML and its immediate
    same-scope dependencies. Its sufficiency must pass offline browser tests
    before it becomes the actual install list.
    """
    mandatory = {
        'index.html', 'offline.html', 'offline-readonly.html',
        'manifest.webmanifest', 'public-runtime-config.js',
        'locale/en.json', 'faq/en.json',
    }
    available = set(included)
    critical = {base + '/' + path for path in mandatory if base + '/' + path in available}
    asset_ref = re.compile(r'(?:src|href)=[\\'"]([^\\'"]+)[\\'"]')
    asset_suffixes = ('.js', '.css', '.svg', '.avif', '.webp', '.png',
                      '.ico', '.woff', '.woff2', '.jpg', '.jpeg')
    for page in ('index.html', 'offline.html', 'offline-readonly.html'):
        current = root / page
        if not current.is_file():
            continue
        for target in asset_ref.findall(current.read_text(encoding='utf-8')):
            asset = target.split('?', 1)[0].split('#', 1)[0]
            if asset.startswith(base + '/') and asset.endswith(asset_suffixes):
                if asset in available:
                    critical.add(asset)
    priority = [item for item in included if item in critical]
    deferred = [item for item in included if item not in critical]
    if base + '/index.html' not in critical or not any(
        '/_next/static/' in item and item.endswith('.js') for item in critical
    ):
        raise ValueError('PWA critical shell is missing landing HTML or Next JavaScript')
    return priority, deferred


def configure_pwa(root: Path, base: str) -> tuple[int, int]:
    worker = root / 'sw.js'
    manifest_file = root / 'manifest.webmanifest'
    if not worker.is_file() or not manifest_file.is_file():
        raise ValueError('PWA Service Worker / Manifest missing from Pages export')

    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict):
        raise ValueError('Invalid PWA manifest')
    def prefix(path: str) -> str:
        if not path.startswith('/') or path.startswith(base + '/'):
            return path
        return base + path

    manifest['start_url'] = prefix(manifest.get('start_url', '/'))
    manifest['scope'] = base + '/'
    manifest['id'] = base + '/'
    for icon in manifest.get('icons', []):
        if isinstance(icon, dict) and isinstance(icon.get('src'), str):
            icon['src'] = prefix(icon['src'])
    for shortcut in manifest.get('shortcuts', []):
        if not isinstance(shortcut, dict):
            continue
        if isinstance(shortcut.get('url'), str):
            shortcut['url'] = prefix(shortcut['url'])
        for icon in shortcut.get('icons', []):
            if isinstance(icon, dict) and isinstance(icon.get('src'), str):
                icon['src'] = prefix(icon['src'])
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    included = []
    digest = hashlib.sha256()
    total_bytes = 0
    for file in sorted(root.rglob('*')):
        if not file.is_file() or file.suffix.lower() not in PWA_SUFFIXES:
            continue
        rel = file.relative_to(root).as_posix()
        if rel in ('sw.js', 'pwa-build.json', 'runtime-config.json'):
            continue
        data = file.read_bytes()
        canonical = BUILD_META.sub('', data.decode('utf-8')).encode('utf-8') if file.suffix.lower() == '.html' else data
        digest.update(rel.encode('utf-8') + b'\x00' + hashlib.sha256(canonical).digest())
        included.append(base + '/' + rel)
        total_bytes += len(canonical)
    html_count = sum(path.endswith('.html') for path in included)
    if not html_count or not any('/_next/static/' in path for path in included):
        raise ValueError('PWA requires exported HTML routes and compiled Next assets')
    if len(included) > 3000 or total_bytes > 480 * 1024 * 1024:
        raise ValueError('PWA precache exceeds supported limits; do not silently omit pages')
    critical, deferred = partition_pwa_resources(root, base, included)
    config = {
        'build_id': digest.hexdigest()[:24],
        'static_export': True,
        'precache': included,
        # Candidate partition only: the existing SW still installs full precache.
        'precache_critical': critical,
        'precache_deferred': deferred,
        'cache_limits': {
            'static': {
                'max_entries': max(500, len(included) + 20),
                'max_age_seconds': 3888000,
                'max_bytes': max(100 * 1024 * 1024, min(536870912, int(total_bytes * 1.25) + 1024 * 1024)),
            },
            'content': {
                'max_entries': 180,
                'max_age_seconds': 604800,
                'max_bytes': 48 * 1024 * 1024,
            },
        },
    }
    (root / 'pwa-build.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # The marker is outside Next's React root and changes only at a real build
    # boundary. Its presence prevents a running previous HTML shell from falsely
    # confirming a successor just because the hashed JS chunks are identical.
    marker = '<meta name="efhc-build-id" content="' + config['build_id'] + '">'
    for page in root.rglob('*.html'):
        html = BUILD_META.sub('', page.read_text(encoding='utf-8'))
        if '</head>' in html:
            html = html.replace('</head>', marker + '</head>', 1)
        elif '<html' in html:
            html = re.sub(r'(<html[^>]*>)', lambda m: m.group(1) + marker, html, count=1)
        else:
            html = marker + html
        page.write_text(html, encoding='utf-8')
    raw = worker.read_text(encoding='utf-8')
    # Idempotent on repeated export normalization. The versioned SW cannot
    # accidentally adopt new deployed build metadata during a running session.
    if raw.startswith('const EFHC_PWA_BUILD_CONFIG = '):
        raw = raw.split('\n', 1)[1]
    prefix_source = 'const EFHC_PWA_BUILD_CONFIG = ' + json.dumps(config, ensure_ascii=False, separators=(',', ':')) + ';\n'
    worker.write_text(prefix_source + raw, encoding='utf-8')
    return html_count, len(included)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--directory', required=True)
    ap.add_argument('--base-path', required=True)
    args = ap.parse_args()
    root = Path(args.directory)
    base = args.base_path.rstrip('/')
    if not base or not re.fullmatch(r'/[A-Za-z0-9_.-]+', base):
        raise ValueError('Invalid Pages repository basePath')
    # Next may generate framework-owned error documents even when their
    # project pages have been physically deleted. Do not ship these artifacts.
    for name in ('404.html', '500.html'):
        (root / name).unlink(missing_ok=True)
    # Next static export can also generate a nested error route.
    # These routes are not part of EFHC's approved offline UI.
    for name in ('404', '500'):
        retired = root / name
        if retired.is_dir():
            shutil.rmtree(retired)
    changed = 0
    for p in root.rglob('*'):
        if not p.is_file() or p.name == 'sw.js' or p.suffix not in ('.html', '.css', '.js'):
            continue
        original = p.read_text(encoding='utf-8')
        updated = PATTERN.sub(lambda m: m.group(1) + base + '/' + m.group(2), original)
        if updated != original:
            p.write_text(updated, encoding='utf-8')
            changed += 1
    fingerprinted = fingerprint_public_stylesheets(root)
    pages, resources = configure_pwa(root, base)
    print(f'EFHC_DEMO_PUBLIC_ASSET_BASEPATH_OK files_rewritten={changed} pages_cached={pages} resources_cached={resources} fingerprinted_css={fingerprinted}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as exc:
        print('EFHC_ASSET_REWRITE_FAIL ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
