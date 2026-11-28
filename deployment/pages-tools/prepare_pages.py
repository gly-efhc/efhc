"""Stage an ephemeral COPY of actual React source for static export.

The imported source tree frontend is never changed by this script.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Pages serves only the React app and a public, nonprivileged runtime config.
# It must never inject browser-owned DEMO identities or financial data.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--target', required=True)
    ap.add_argument('--base-path', required=True)
    args = ap.parse_args()
    base = args.base_path.rstrip('/')
    if base and (not base.startswith('/') or '/' in base[1:] or base in ('/.', '/..')):
        raise ValueError('base-path must be empty or /single-repository-name')
    source, target = Path(args.source), Path(args.target)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    # The canonical Next config and shared React components select their own
    # build profile. Do not rewrite either in the staged source.
    # GitHub Pages cannot execute Next API handlers. Keep all real USER/ADMIN React pages.
    api = target / 'src/pages/api'
    if api.exists():
        shutil.rmtree(api)
    # Pages Router custom _error has getInitialProps and cannot be statically exported.
    custom_error = target / 'src/pages/_error.tsx'
    if custom_error.exists():
        custom_error.unlink()
    (target / 'public/public-runtime-config.js').write_text(
        'window.__EFHC_PUBLIC_CONFIG__=Object.freeze({});\n', encoding='utf-8')
    owner = os.environ.get('GITHUB_REPOSITORY_OWNER', 'gly-efhc')
    if not owner or not owner.replace('-', '').isalnum():
        raise ValueError('Invalid Pages owner in TONConnect manifest')
    public_url = f'https://{owner}.github.io{base}'
    manifest = {'url': public_url, 'name': 'EFHC Browser DEMO',
                'iconUrl': public_url + '/icon.png',
                'termsOfUseUrl': public_url + '/web-profile/?legal=terms',
                'privacyPolicyUrl': public_url + '/web-profile/?legal=privacy'}
    (target / 'public/tonconnect-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Retain the shared PWA shell; build-specific Pages scope is set after export.
    (target / 'public/runtime-config.json').unlink(missing_ok=True)
    # The DEMO backend receives business requests over its explicit HTTPS origin.
    print(f'EFHC_PAGES_TEMP_BUILD_READY base={base!r} source={source} target={target}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f'EFHC_PAGES_PREPARE_FAIL: {exc}', file=sys.stderr)
        raise SystemExit(1)
