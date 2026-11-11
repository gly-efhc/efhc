#!/usr/bin/env python3
"""Reject additions of work-number identities; retain existing debt in place."""

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys


POLICY_PATH = 'site/ci/work-prefix-exceptions.json'
IDENTITIES_PATH = 'site/frontend/src/design-system/source-identities.json'
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


def read_policy(ref):
    raw = git('show', ref + ':' + POLICY_PATH)
    policy = json.loads(raw)
    if policy.get('schema') != 1 or set(policy) != {'schema', 'exceptions'}:
        raise ValueError('invalid exception policy')
    for item in policy['exceptions']:
        if set(item) != {'path', 'literal', 'kind', 'reason'}:
            raise ValueError('exception must specify exact path, literal, kind and reason')
        if not item['reason'].strip() or not item['literal'] or any(x in item['path'] for x in ('*', '?', '..')):
            raise ValueError('blanket/undocumented exceptions are forbidden')
        if item['kind'] == 'external-action':
            if not re.fullmatch(r'[\w-]+/[\w./-]+@v\d+(?:\.\d+)*', item['literal']):
                raise ValueError('invalid external action version exception')
        elif item['kind'] == 'protocol':
            if not re.fullmatch(r'/[\w/-]+/v\d+/?|https://[^\s]+', item['literal']):
                raise ValueError('protocol exception must be an exact external address or API path')
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
    elif path == 'site/frontend/package-lock.json':
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
    if path == POLICY_PATH:
        return found
    for item in policy['exceptions']:
        if path == item['path']:
            text = text.replace(item['literal'], '')
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
    return found


def source_aliases(new, base):
    """Validate inert provenance, never an exemption for live identifiers.

    Only aliases physically present in an ancestor may be recorded; destinations
    must be stable and unique. An approved rename may transfer remaining debt,
    but a copy or new prefix still fails. The frozen sources stay unchanged.
    """
    if IDENTITIES_PATH not in new:
        return {}
    document = json.loads(blob(new[IDENTITIES_PATH]))
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


def inspect(base, head, policy_ref):
    old, new = tree(base), tree(head)
    policy = read_policy(policy_ref)
    aliases = source_aliases(new, base)
    failures = []
    checked = 0
    # A PR cannot grant itself exceptions. Initial installation is the only case
    # in which the trusted policy ref is the candidate, pinned by the workflow.
    if new.get(POLICY_PATH) != tree(policy_ref).get(POLICY_PATH):
        failures.append({'path': POLICY_PATH, 'identity': 'exception policy changed; requires separate OWNER-controlled installation', 'added': 1})
    for path, entry in new.items():
        if old.get(path) == entry:
            continue
        checked += 1
        if path == IDENTITIES_PATH:
            continue  # validated source provenance, never imported by runtime
        current = identities(path, blob(entry), policy)
        previous_path = path if path in old else next((prior for prior, stable in aliases.items()
                                                     if stable == path and prior in old and prior not in new), None)
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
