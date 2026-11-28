#!/usr/bin/env python3
"""Reject additions of work-number identities; retain existing debt in place."""

import argparse
import base64
import hashlib
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys


LEGACY_POLICY_PATH = 'site/ci/work-prefix-exceptions.json'
POLICY_PATH = 'scripts/ci/work-prefix-exceptions.json'
# Exact relocation of the already-reviewed manifest, with identical bytes.
APPROVED_POLICY_RELOCATION_DIGEST = '229b5d380ec940381225743c44478bbb9c30a09c176687ebcfec1c7de2cedb4d'
# OWNER-approved exact manifest transition. This code must be trusted on the
# target branch before installation; a policy edit cannot add its own pin.
APPROVED_POLICY_TRANSITIONS = {
    '5e3d98a3a5d78821e522ecb0bbe383dc831d5cd8c23ef15d80a38449a9e0e646':
        '01193a64c0f312b6b8932359664cbbe3880c0f4dd388fe6af2fa54d04fac70d3',
    '01193a64c0f312b6b8932359664cbbe3880c0f4dd388fe6af2fa54d04fac70d3':
        '5341b4fe05774e77c6079227c91f325c0196c09e801756f56f2e24e533c50a67',
    '5341b4fe05774e77c6079227c91f325c0196c09e801756f56f2e24e533c50a67':
        '184f7e88354e23527fb11b76721e3e8754cc02ec3924535abe05ffa013a5e718',
    '184f7e88354e23527fb11b76721e3e8754cc02ec3924535abe05ffa013a5e718':
        '229b5d380ec940381225743c44478bbb9c30a09c176687ebcfec1c7de2cedb4d',
    '67a6510c74031e83f19e7940543537117ff135c0e4bcac23986ef8f890bff09f':
        'b1e44354e07b7e508c34c769c33f1d0924c96fde9a5adac9caf00a50b6057b63',
    'b1e44354e07b7e508c34c769c33f1d0924c96fde9a5adac9caf00a50b6057b63':
        '5e3d98a3a5d78821e522ecb0bbe383dc831d5cd8c23ef15d80a38449a9e0e646',
}

IDENTITIES_PATH = 'frontend/src/design-system/source-identities.json'
LEGACY_IDENTITIES_PATH = 'site/frontend/src/design-system/source-identities.json'
TOKEN = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*(?:[-.][A-Za-z0-9_$]+)*')
SEGMENT = re.compile(
    r'(?:^|[-_.])(?:v|cycles?|iterations?|iter|it|revision|rev|release|build|patch)[_-]?\d+'
    r'|(?:^|[-_.])c\d{2,}', re.IGNORECASE,
)
CAMEL = re.compile(r'(?<=[a-z0-9])(?:V\d+|C\d{2,}|Cycle[_-]?\d+|Iteration[_-]?\d+|Revision[_-]?\d+|Release[_-]?\d+|Build[_-]?\d+|Patch[_-]?\d+)')
DOM_WORK_VALUE = re.compile(
    r'(data-[\w-]*(?:cycle|iteration|version|revision)[\w-]*)\s*=\s*'
    r'(?:[\"\']([vV]?\d+)[\"\']|\{(\d+)\})', re.IGNORECASE,
)
SOURCE_SUFFIXES = {'.py', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.css', '.scss', '.html', '.json', '.yml', '.yaml', '.sh'}
QUOTED_HASH = re.compile(r'([\"\'])[a-f0-9]{40}(?:[a-f0-9]{24})?\1', re.IGNORECASE)
COLOR_VALUE = re.compile(r'(?<=:)\s*#(?:[a-f0-9]{8}|[a-f0-9]{6}|[a-f0-9]{4}|[a-f0-9]{3})(?![\w-])', re.IGNORECASE)
SVG_PATH = re.compile(r'([\"\'])[Mm][-+0-9.,\sMmLlHhVvCcSsQqTtAaZzEe]*\1')
BINARY_IMAGE = re.compile(r'data:image/(webp|png|jpeg|gif|avif);base64,([A-Za-z0-9+/]+={0,2})')
CSS_DECLARATION = re.compile(r'(?<=[;{])(\s*[-\w]+\s*:)([^{};]*)(?=;|\})')
HEX_COLOR = re.compile(r'#(?:[a-f0-9]{8}|[a-f0-9]{6}|[a-f0-9]{4}|[a-f0-9]{3})(?![\w-])', re.IGNORECASE)


def binary_image(match):
    raw = base64.b64decode(match[2], validate=True)
    valid = {'webp': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP',
             'png': raw.startswith(b'\x89PNG\r\n\x1a\n'),
             'jpeg': raw.startswith(b'\xff\xd8'),
             'gif': raw.startswith((b'GIF87a', b'GIF89a')),
             'avif': raw[4:8] == b'ftyp' and b'avif' in raw[8:32]}
    if not valid[match[1]]:
        raise ValueError('invalid opaque image payload')
    return 'binary-image-data'


def git(*args):
    return subprocess.check_output(['git', *args])


def resolve(ref):
    # Resolve before constructing any object specifications. No shell evaluation.
    return git('rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()


def tree(ref):
    result = {}
    for record in git('ls-tree', '-r', '-z', ref).split(b'\0'):
        if record:
            metadata, path = record.split(b'\t', 1)
            mode, kind, sha = metadata.decode().split()
            result[path.decode('utf-8')] = (mode, kind, sha)
    return result


def blob(entry):
    if entry[1] != 'blob':
        raise ValueError('unreviewed submodule cannot bypass identifier inspection')
    return git('cat-file', 'blob', entry[2])


def policy_path(entries):
    paths = [path for path in (LEGACY_POLICY_PATH, POLICY_PATH) if path in entries]
    if len(paths) != 1 or entries[paths[0]][:2] != ('100644', 'blob'):
        raise ValueError('exactly one regular policy manifest required')
    return paths[0]


def read_policy(ref):
    entries = tree(ref)
    raw = blob(entries[policy_path(entries)])
    policy = json.loads(raw)
    if policy.get('schema') != 1 or set(policy) != {'schema', 'exceptions'}:
        raise ValueError('invalid exception policy')
    contract_records = set()
    for item in policy['exceptions']:
        fields = {'path', 'literal', 'kind', 'reason'}
        if item.get('kind') == 'verified-contract':
            fields.add('max_count')
        if set(item) != fields:
            raise ValueError('exception must specify exact path, literal, kind and reason')
        if not item['reason'].strip() or not item['literal'] or any(x in item['path'] for x in ('*', '?', '..')):
            raise ValueError('blanket/undocumented exceptions are forbidden')
        if item['kind'] == 'external-action':
            if not re.fullmatch(r'[\w-]+/[\w./-]+@v\d+(?:\.\d+)*', item['literal']):
                raise ValueError('invalid external action version exception')
        elif item['kind'] == 'protocol':
            if not re.fullmatch(r'/(?:[\w-]+/)*v\d+/?|https://[^\s]+', item['literal']):
                raise ValueError('protocol exception must be an exact external address or API path')
        elif item['kind'] == 'external-identifier':
            if not TOKEN.fullmatch(item['literal']) or not (SEGMENT.search(item['literal']) or CAMEL.search(item['literal'])):
                raise ValueError('invalid external identifier exception')
        elif item['kind'] == 'signed-prefix':
            if not re.fullmatch(r'[a-z][a-z0-9-]*-v[0-9]+/', item['literal']):
                raise ValueError('invalid signed prefix exception')
        elif item['kind'] == 'external-label':
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 .-]* v[0-9]+(?:\.[0-9]+)*', item['literal']):
                raise ValueError('invalid external product version label')
        elif item['kind'] == 'dependency-comment':
            if Path(item['path']).name != 'requirements.txt' or not re.fullmatch(r'#[^\r\n]+', item['literal']):
                raise ValueError('invalid exact requirements comment exception')
        elif item['kind'] == 'verified-contract':
            field, sep, token = item['literal'].partition(':')
            pathname = Path(item['path'])
            key = (item['path'], item['literal'])
            if (not sep or type(item['max_count']) is not int or not 1 <= item['max_count'] <= 16
                    or key in contract_records or pathname.is_absolute()
                    or not (SEGMENT.search(token) or CAMEL.search(token))
                    or not ((field == 'path' and token == pathname.name and item['max_count'] == 1)
                            or (field == 'identifier' and TOKEN.fullmatch(token)))):
                raise ValueError('invalid bounded contract identity exception')
            contract_records.add(key)
        elif item['kind'] != 'historical-source':
            raise ValueError('unknown exception kind')
    return policy


# Exempt recognized metadata values, never entire files, source names or scripts.
WORKFLOW_FILE = re.compile(r'^\.github/workflows/[^/]+\.ya?ml$')
OFFICIAL_ACTION_USE = re.compile(
    r'(?m)^([ \t]*(?:-[ \t]*)?uses:[ \t]*)'
    r'(actions/(?:checkout|setup-node)@v\d+(?:\.\d+)*)'
    r'([ \t]*(?:#.*)?)$'
)
BRANCH_NAME = r'cycle\d{4}/iteration\d{2}-[a-z0-9][a-z0-9._-]*'
BRANCH_ITEM = re.compile(r'^([ \t]*-[ \t]+)(' + BRANCH_NAME + r')([ \t]*(?:#.*)?)$')
BRANCH_REF = re.compile(r'\brefs/heads/' + BRANCH_NAME + r'\b')
GIT_COMMIT_MESSAGE = re.compile(
    r'''(?m)^([ \t]*git[ \t]+commit[ \t]+-m[ \t]+)(['"])(.*?)\2([ \t]*)$'''
)
LOCK_INTEGRITY = re.compile(
    r'("integrity"\s*:\s*")sha(256|384|512)-([A-Za-z0-9+/]+={0,2})(")'
)


def mask_external_metadata(path, text):
    if WORKFLOW_FILE.fullmatch(path):
        text = OFFICIAL_ACTION_USE.sub(
            lambda match: match[1] + 'official-action-reference' + match[3], text
        )
        text = BRANCH_REF.sub('git-branch-reference', text)
        text = GIT_COMMIT_MESSAGE.sub(
            lambda match: match[1] + match[2] + 'commit-message' + match[2] + match[4],
            text,
        )
        # Only items directly nested under a workflow branches: filter.
        branch_indent = None
        lines = []
        for line in text.splitlines(keepends=True):
            stripped = line.rstrip('\r\n')
            spaces = len(stripped) - len(stripped.lstrip(' '))
            branch_key = re.fullmatch(r'[ \t]*branches:[ \t]*(?:#.*)?', stripped)
            if branch_key:
                branch_indent = spaces
            elif stripped.strip() and branch_indent is not None:
                if spaces <= branch_indent:
                    branch_indent = None
                else:
                    line = BRANCH_ITEM.sub(
                        lambda match: match[1] + 'git-branch-reference' + match[3],
                        stripped,
                    ) + line[len(stripped):]
            lines.append(line)
        text = ''.join(lines)
    elif path in ('frontend/package-lock.json', 'site/frontend/package-lock.json'):
        lock = json.loads(text)
        if (not isinstance(lock, dict)
                or not isinstance(lock.get('lockfileVersion'), int)
                or not isinstance(lock.get('packages'), dict)):
            raise ValueError('invalid npm package-lock metadata')
        def mask_integrity(match):
            digest = base64.b64decode(match[3], validate=True)
            if len(digest) != {'256': 32, '384': 48, '512': 64}[match[2]]:
                raise ValueError('invalid npm integrity digest')
            return match[1] + 'npm-integrity-digest' + match[4]
        text = LOCK_INTEGRITY.sub(mask_integrity, text)
    return text

def mask_exact_exception(text, item):
    literal = item['literal']
    quoted = re.escape(literal)
    kind = item['kind']
    if kind == 'external-identifier':
        return TOKEN.sub(lambda match: ' ' * len(literal) if match[0] == literal else match[0], text)
    if kind == 'signed-prefix':
        return re.sub(r"""(?<![\w'"])b(["'])""" + quoted + r'\1', ' ', text)
    if kind == 'dependency-comment':
        return re.sub(r'(?m)^' + quoted + r'(?=\r?$)', ' ', text)
    if kind in {'external-label', 'protocol'}:
        left = r'(?<![\w$.-])' if not literal.startswith('/') else ''
        right = r'(?![\w$-]|\.[\w])'
        return re.sub(left + quoted + right, ' ', text)
    return text.replace(literal, ' ')


def identities(path, content, policy):
    found = Counter()
    for part in path.split('/'):
        if SEGMENT.search(part) or CAMEL.search(part):
            found['path:' + part] += 1
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        if Path(path).suffix.lower() in SOURCE_SUFFIXES:
            raise ValueError('non-UTF-8 working source cannot be inspected')
        return found
    if '\0' in text:
        if Path(path).suffix.lower() in SOURCE_SUFFIXES:
            raise ValueError('NUL in working source cannot bypass inspection')
        return found
    # This metadata file is validated from the trusted ref, not excluded by glob.
    # Candidate edits to policy are rejected separately, including new exemptions.
    if path in (LEGACY_POLICY_PATH, POLICY_PATH):
        return found
    for item in policy['exceptions']:
        if path == item['path'] and item['kind'] != 'verified-contract':
            text = mask_exact_exception(text, item)
    # Full quoted Git/SHA checksums and CSS declaration values are data, not
    # work-number identities. Selectors/function names are still inspected.
    text = QUOTED_HASH.sub('"checksum"', text)
    text = COLOR_VALUE.sub(' color', text)
    text = SVG_PATH.sub('"svg-path"', text)
    text = BINARY_IMAGE.sub(binary_image, text)
    text = CSS_DECLARATION.sub(lambda match: match[1] + HEX_COLOR.sub('color', match[2]), text)
    text = mask_external_metadata(path, text)
    for match in TOKEN.finditer(text):
        token = match.group()
        if SEGMENT.search(token) or CAMEL.search(token):
            found['identifier:' + token] += 1
    for match in DOM_WORK_VALUE.finditer(text):
        found['attribute:' + match[1] + '=' + (match[2] or match[3])] += 1
    for item in policy['exceptions']:
        if item['kind'] == 'verified-contract' and item['path'] == path:
            key = item['literal']
            if found[key]:
                found[key] -= min(found[key], item['max_count'])
                if not found[key]:
                    del found[key]
    return found


def provenance_path(entries):
    paths = [path for path in (LEGACY_IDENTITIES_PATH, IDENTITIES_PATH) if path in entries]
    if len(paths) > 1 or (paths and entries[paths[0]][:2] != ('100644', 'blob')):
        raise ValueError('ambiguous or invalid historical identity mapping')
    return paths[0] if paths else None


def source_aliases(new, base):
    """Validate inert provenance, never an exemption for live identifiers.

    Only aliases physically present in an ancestor may be recorded; destinations
    must be stable and unique. An approved rename may transfer remaining debt,
    but a copy or new prefix still fails. The frozen sources stay unchanged.
    """
    path = provenance_path(new)
    if path is None:
        return {}
    document = json.loads(blob(new[path]))
    if set(document) != {'source_commit', 'aliases'}:
        raise ValueError('invalid historical identity mapping')
    source = document['source_commit']
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('identity source must be a pinned ancestor commit')
    git('merge-base', '--is-ancestor', source, base)
    originals = tree(source)
    content = b'\n'.join(blob(entry) for entry in originals.values() if entry[1] == 'blob')
    aliases = document['aliases']
    if not isinstance(aliases, dict) or len(set(aliases.values())) != len(aliases):
        raise ValueError('identity collisions are forbidden')
    for previous, stable in aliases.items():
        if not previous or previous.encode() not in content and previous not in originals:
            raise ValueError('historical alias is absent from its pinned source')
        if not stable or identities(stable, stable.encode(), {'exceptions': []}):
            raise ValueError('destination is not a stable functional identity')
        if any(x in stable for x in ('..', '\n', '\0')):
            raise ValueError('invalid identity destination')
    return aliases


def exact_policy_installation(old, new, trusted):
    if old != trusted:
        return False
    old_path, new_path = policy_path(old), policy_path(new)
    before, after = old[old_path], new[new_path]
    changed_paths = {path for path in old.keys() | new.keys() if old.get(path) != new.get(path)}
    if old_path != new_path:
        return (old_path == LEGACY_POLICY_PATH and new_path == POLICY_PATH
                and changed_paths == {old_path, new_path} and before == after
                and hashlib.sha256(blob(before)).hexdigest() == APPROVED_POLICY_RELOCATION_DIGEST)
    if changed_paths != {old_path}:
        return False
    expected = APPROVED_POLICY_TRANSITIONS.get(hashlib.sha256(blob(before)).hexdigest())
    return expected == hashlib.sha256(blob(after)).hexdigest()


def inspect(base, head, policy_ref):
    old, new = tree(base), tree(head)
    trusted = tree(policy_ref)
    trusted_path, candidate_path = policy_path(trusted), policy_path(new)
    policy = read_policy(policy_ref)
    aliases = source_aliases(new, base)
    prior_aliases = {}
    old_map, new_map = provenance_path(old), provenance_path(new)
    if old_map and new_map and (old_map != new_map or old[old_map] != new[new_map]):
        old_source = json.loads(blob(old[old_map]))['source_commit']
        new_source = json.loads(blob(new[new_map]))['source_commit']
        if old_source == new_source:
            prior_aliases = source_aliases(old, base)
    used_previous_paths = set()
    failures = []
    checked = 0
    # Only the already-trusted checker may authorize a standalone, exact policy
    # installation. The candidate cannot approve mixed code or policy changes.
    if candidate_path != trusted_path or new[candidate_path] != trusted[trusted_path]:
        if exact_policy_installation(old, new, trusted):
            policy = read_policy(head)
        else:
            failures.append({'path': POLICY_PATH, 'identity': 'exception policy changed; requires separate OWNER-controlled installation', 'added': 1})
    for path, entry in new.items():
        if old.get(path) == entry:
            continue
        checked += 1
        if path == new_map:
            continue  # validated source provenance, never imported by runtime
        current = identities(path, blob(entry), policy)
        previous_path = path if path in old else next((prior for prior, stable in aliases.items()
                                                     if stable == path and prior in old and prior not in new), None)
        if previous_path is None:
            # A repeated historical relocation can carry only the identical blob
            # from its validated, now-removed prior destination. No new debt.
            previous_path = next((prior_aliases[prior] for prior, stable in aliases.items()
                                  if stable == path and prior in prior_aliases
                                  and prior_aliases[prior] in old and prior_aliases[prior] not in new
                                  and old[prior_aliases[prior]] == entry), None)
        if previous_path and previous_path != path:
            if previous_path in used_previous_paths:
                raise ValueError('historical source reused for multiple destinations')
            used_previous_paths.add(previous_path)
        previous = identities(previous_path, blob(old[previous_path]), policy) if previous_path else Counter()
        # The old filename is not carried into the new path. Contents retain the
        # old allowance until each dependency has actually been cleaned up.
        if previous_path and previous_path != path:
            current = Counter({key: count for key, count in current.items() if not key.startswith('path:')})
        for identity, count in (current - previous).items():
            failures.append({'path': path, 'identity': identity, 'added': count})
    return {'guard': 'NO_WORK_PREFIXES', 'base': base, 'head': head,
            'checked_files': checked, 'status': 'FAIL' if failures else 'PASS', 'violations': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--policy-ref', help='trusted ref; defaults to base')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        base, head = resolve(args.base), resolve(args.head)
        result = inspect(base, head, resolve(args.policy_ref or args.base))
    except (ValueError, KeyError, UnicodeError, subprocess.CalledProcessError) as error:
        print('NO_WORK_PREFIXES FAIL: inspection could not complete (' + type(error).__name__ + ')', file=sys.stderr)
        return 2
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.write_text(encoded)
    print(encoded, end='')
    return 1 if result['violations'] else 0


if __name__ == '__main__':
    sys.exit(main())
