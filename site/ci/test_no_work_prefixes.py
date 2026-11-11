"""Exercise real Git snapshots and negative exit statuses without runtime changes."""

import importlib.util
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('no_work_prefixes.py')
spec = importlib.util.spec_from_file_location('prefix_guard', SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PrefixGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'guard@example.invalid')
        self.git('config', 'user.name', 'Guard test')
        self.policy = {'schema': 1, 'exceptions': []}
        self.put(guard.POLICY_PATH, json.dumps(self.policy))
        self.put('src/header.css', '.header { color: inherit; }\n')
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args]).decode().strip()

    def put(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'guard fixture')
        return self.git('rev-parse', 'HEAD')

    def check(self, expected, base=None):
        result = subprocess.run(
            ['python3', str(SCRIPT), '--base', base or self.base, '--head', 'HEAD'],
            cwd=self.root, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def test_stable_source_change_passes(self):
        self.put('src/header.css', '.header { color: currentColor; }\n')
        self.commit()
        self.assertEqual(self.check(0)['checked_files'], 1)

    def test_new_filename_fails(self):
        self.put('src/header-' + 'v' + '123.css', '.header {}')
        self.commit()
        self.assertTrue(self.check(1)['violations'])

    def test_all_work_identities_fail_in_arbitrary_working_files(self):
        markers = ['v' + '123', 'cycle' + '0036', 'iteration_' + '01',
                   'c' + '0034', 'iter-' + '02', 'revision' + '42',
                   'release_' + '99', 'build' + '42']
        for marker in markers:
            with self.subTest(marker=marker):
                self.put('arbitrary.asset', 'name_' + marker)
                self.commit()
                self.check(1)

    def test_camel_function_and_variable_names_fail(self):
        for marker in ['V' + '123', 'Cycle' + '0036', 'Iteration_' + '03', 'C' + '0034']:
            self.put('src/runtime.ts', 'const header' + marker + ' = 1;')
            self.commit()
            self.check(1)

    def test_css_and_dom_attributes_fail(self):
        self.put('src/header.css', '.header-' + 'cycle' + '0036 { color: inherit; }')
        self.put('src/layout.tsx', '<div data-header-' + 'cycle' + '="0007" />')
        self.commit()
        violations = self.check(1)['violations']
        self.assertTrue(any(x['identity'].startswith('attribute:') for x in violations))
        self.assertTrue(any(x['path'].endswith('.css') for x in violations))

    def test_legacy_occurrence_can_remain_but_not_grow(self):
        legacy = '.header-' + 'v' + '123'
        self.put('src/header.css', legacy + ' { color: inherit; }')
        base = self.commit()
        self.put('src/header.css', legacy + ' { color: currentColor; }')
        self.commit()
        self.check(0, base)
        self.put('src/header.css', (legacy + ' {}\n') * 2)
        self.commit()
        self.check(1, base)

    def test_debt_cannot_be_moved_to_another_file(self):
        self.put('src/header.css', '.header-' + 'v' + '123 {}')
        base = self.commit()
        (self.root / 'src/header.css').rename(self.root / 'src/header-layout.css')
        self.commit()
        self.check(1, base)

    def test_removed_debt_cannot_return_after_cleanup(self):
        self.put('src/header.css', '.header-' + 'v' + '123 {}')
        self.commit()
        self.put('src/header.css', '.header {}')
        clean = self.commit()
        self.put('src/header.css', '.header-' + 'v' + '123 {}')
        self.commit()
        self.check(1, clean)

    def test_unchanged_historical_reference_is_preserved(self):
        self.put('reference/FRONTEND_' + 'v' + '866.html', '<html />')
        base = self.commit()
        self.put('src/header.css', '.header { color: currentColor; }')
        self.commit()
        self.check(0, base)

    def test_exact_protocol_and_action_exceptions_only(self):
        action = 'actions/checkout@' + 'v' + '7'
        protocol = '/api/' + 'v' + '1'
        self.policy['exceptions'] = [
            {'path': '.github/workflows/check.yml', 'literal': action, 'kind': 'external-action', 'reason': 'third-party version'},
            {'path': 'src/api.ts', 'literal': protocol, 'kind': 'protocol', 'reason': 'existing server protocol'},
        ]
        self.put(guard.POLICY_PATH, json.dumps(self.policy))
        base = self.commit()
        self.put('.github/workflows/check.yml', 'uses: ' + action)
        self.put('src/api.ts', 'const endpoint = "' + protocol + '";')
        self.commit()
        self.check(0, base)
        self.put('src/other.ts', 'const endpoint = "' + protocol + '";')
        self.commit()
        self.check(1, base)


    def test_exact_workflow_metadata_is_not_runtime_code(self):
        branch = 'cycle' + '0045/iteration' + '22-official-tonconnect-ui-react'
        action = 'actions/checkout@' + 'v' + '4'
        message = 'build(c' + '0045): completed official wallet migration'
        workflow = '\n'.join([
            'on:',
            '  push:',
            '    branches:',
            '      - ' + branch,
            'jobs:',
            '  install:',
            '    if: github.ref == ' + repr('refs/heads/' + branch),
            '    steps:',
            '      - uses: ' + action,
            '      - run: |',
            "          git commit -m '" + message + "'",
            '          git push origin HEAD:refs/heads/' + branch,
        ]) + '\n'
        self.put('.github/workflows/official-wallet.yml', workflow)
        self.commit()
        self.check(0)

    def test_workflow_script_and_unrelated_values_remain_guarded(self):
        marker = 'widgetCycle' + '0045'
        branch = 'cycle' + '0045/iteration' + '22-wallet'
        self.put('.github/workflows/official-wallet.yml', '\n'.join([
            'on:',
            '  push:',
            '    branches:',
            '      - ' + branch,
            'jobs:',
            '  build:',
            '    steps:',
            '      - uses: actions/checkout@' + 'v' + '4',
            '      - run: |',
            '          const ' + marker + ' = true;',
        ]))
        self.commit()
        self.assertTrue(any(marker in row['identity'] for row in self.check(1)['violations']))
        self.put('src/code.ts', 'const ' + marker + ' = 1;')
        self.commit()
        self.check(1)

    def test_only_exact_external_action_fields_are_exempt(self):
        action = 'actions/checkout@' + 'v' + '4'
        self.put('.github/workflows/action.yml', 'env:\n  EXTERNAL: ' + action + '\n')
        self.commit()
        self.check(1)

    def test_npm_integrity_is_data_but_application_names_remain_guarded(self):
        digest = 'sha' + '512-b' + 'V' + '4' + 'A' * 83 + '=='
        self.assertEqual(len(base64.b64decode(digest[7:], validate=True)), 64)
        lock = {'name': 'frontend', 'lockfileVersion': 3, 'packages': {
            '': {'integrity': digest}
        }}
        self.put('site/frontend/package-lock.json', json.dumps(lock))
        self.commit()
        self.check(0)
        lock['packages']['']['runtimeName'] = 'buttonCycle' + '0045'
        self.put('site/frontend/package-lock.json', json.dumps(lock))
        self.commit()
        self.check(1)
        del lock['packages']['']['runtimeName']
        lock['packages']['']['integrity'] = 'sha512-' + 'AAAA'
        self.put('site/frontend/package-lock.json', json.dumps(lock))
        self.commit()
        self.check(2)


    def test_candidate_cannot_grant_itself_exception(self):
        self.policy['exceptions'] = [{'path': 'src/other.ts', 'literal': '/api/' + 'v' + '1', 'kind': 'protocol', 'reason': 'self-approved'}]
        self.put(guard.POLICY_PATH, json.dumps(self.policy))
        self.put('src/other.ts', 'const endpoint = "/api/' + 'v' + '1";')
        self.commit()
        self.check(1)

    def test_missing_baseline_fails_closed(self):
        self.check(2, 'missing-reference')

    def test_binary_filename_is_checked(self):
        self.put('assets/header-' + 'cycle' + '0036.png', b'\xff\x00')
        self.commit()
        self.check(1)

    def test_malformed_source_cannot_hide_identifiers(self):
        self.put('src/hidden.ts', b'\xff\x00')
        self.commit()
        self.check(2)

    def test_checksum_metadata_is_not_a_work_identity(self):
        digest = 'c' + '123' + 'a' * 36
        self.put('metadata.json', json.dumps({'commit': digest, 'sha256': digest + 'b' * 24}))
        self.commit()
        self.check(0)
        self.put('src/runtime.ts', 'const ' + digest + ' = 1;')
        self.commit()
        self.check(1)

    def test_css_color_data_is_not_a_selector_exemption(self):
        color = 'c' + '00334'
        self.put('src/header.css', '.header { color: #' + color + '; }')
        self.commit()
        self.check(0)
        self.put('src/header.css', '#' + color + ' { color: inherit; }')
        self.commit()
        self.check(1)

    def test_internationalization_is_not_an_iteration(self):
        self.put('src/i' + '18n.ts', 'const i' + '18nKey = "language";')
        self.commit()
        self.check(0)

    def test_validated_historical_rename_retains_only_previous_debt(self):
        old = 'src/header-' + 'v' + '123.css'
        self.put(old, '.header-' + 'v' + '123 {}')
        base = self.commit()
        self.put(guard.IDENTITIES_PATH, json.dumps({'source_commit': base, 'aliases': {old: 'src/header-layout.css'}}))
        (self.root / old).rename(self.root / 'src/header-layout.css')
        self.commit()
        self.check(0, base)
        self.put('src/header-layout.css', ('.header-' + 'v' + '123 {}\n') * 2)
        self.commit()
        self.check(1, base)

    def test_historical_map_cannot_invent_identity_or_keep_original_copy(self):
        old = 'src/header-' + 'v' + '123.css'
        self.put(old, '.header-' + 'v' + '123 {}')
        base = self.commit()
        self.put(guard.IDENTITIES_PATH, json.dumps({'source_commit': base, 'aliases': {old: 'src/header-layout.css'}}))
        self.put('src/header-layout.css', '.header-' + 'v' + '123 {}')
        self.commit()
        self.check(1, base)
        self.put(guard.IDENTITIES_PATH, json.dumps({'source_commit': base, 'aliases': {'absent-' + 'v' + '999': 'stable'}}))
        self.commit()
        self.check(2, base)

    def test_binary_image_data_is_preserved_but_cannot_hide_selector_names(self):
        raw = b'RIFF\x00\x00\x00\x00WEBP' + b'v' + b'123'
        uri = 'data:image/webp;base64,' + base64.b64encode(raw).decode()
        self.put('src/header.css', '.header { background:url("' + uri + '"); }')
        self.commit()
        self.check(0)
        self.put('src/header.css', '.header-' + 'v' + '123 { background:url("' + uri + '"); }')
        self.commit()
        self.check(1)

    def test_gradient_color_is_data_but_descendant_id_is_an_identity(self):
        color = '#' + '4c' + '81c8'
        self.put('src/header.css', '.header { background:linear-gradient(' + color + ',#000); }')
        self.commit()
        self.check(0)
        self.put('src/header.css', '.header #' + 'c' + '00334 { color: inherit; }')
        self.commit()
        self.check(1)


if __name__ == '__main__':
    unittest.main()
