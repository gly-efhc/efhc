"""Extract only public renderer contracts from the OWNER-selected v866 archive.

No backend, ENV, credentials or private project documentation is copied.
The archive and both HTML hashes must match the recorded immutable authority.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

KEYS = ('REGISTRY', 'SOURCE_STYLE', 'DEFAULTS', 'HEADER_THEME_COMPOSITION',
        'COLOR_THEME_CATALOG', 'COLOR_TO_RUNTIME_LEGACY_THEME',
        'RANK_STYLE_ID_BY_SELECTION')


def extract(archive, contract):
    data = json.loads(contract.read_text(encoding='utf-8'))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != data['source']['archive_sha256']:
        raise ValueError('archive is not the recorded v866 authority')
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        if len(names) != len(set(names)) or source.testzip():
            raise ValueError('invalid archive entries/CRC')
        html = source.read('FRONTEND_v866.html')
    if hashlib.sha256(html).hexdigest() != data['source']['html_sha256']:
        raise ValueError('HTML authority SHA mismatch')
    text = html.decode('utf-8')
    for key in KEYS:
        match = re.search(r'const ' + key + r'\s*=\s*Object.freeze\(', text)
        if match is None:
            raise ValueError(f'missing HTML contract: {key}')
        data[key] = json.JSONDecoder().raw_decode(text[match.end():])[0]
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = extract(args.archive, args.contract)
    if args.check:
        if result != json.loads(args.contract.read_text(encoding='utf-8')):
            raise SystemExit('HTML/contract drift')
        print('HTML_V866_CONTRACT_PARITY=PASS')
    else:
        args.contract.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
