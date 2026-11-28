"""Collect independent, nonblocking EFHC Pages diagnostics with genuine tool outputs.

The public importer contains frontend and Pages tools only. Full backend FAST/FULL
and private TONConnect workflow coverage are reported as NOT_AVAILABLE, not PASS.
This script never writes the application source and never invokes a shell.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

SCHEMA = 'efhc.pages.quality-evidence.v1'
SENSITIVE = re.compile(r'(?i)(password|token|secret|authorization|api[_-]?key)\s*[:=]\s*([^\s,;]+)')


async def execute(command: list[str], cwd: Path, timeout: int, name: str, output: Path) -> tuple[int, str]:
    """Execute only explicit argv, without shell interpretation or credential printing."""
    environment = {**os.environ, 'PIP_DISABLE_PIP_VERSION_CHECK': '1'}
    if name == 'frontend-performance-budgets':
        environment['EFHC_BUDGET_OUTPUT'] = str(output / 'frontend-performance-budgets.json')
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise
    output = stdout.decode('utf-8', 'replace')
    if stderr:
        output += '\n[stderr]\n' + stderr.decode('utf-8', 'replace')
    return process.returncode or 0, output


def check(
    name: str,
    command: list[str] | None,
    cwd: Path,
    output: Path,
    timeout: int = 180,
    reason: str = '',
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    result = {
        'check': name, 'status': 'NOT_AVAILABLE', 'command': command or [],
        'reason': reason, 'duration_sec': 0,
    }
    if command is None:
        (output / f'{name}.log').write_text('NOT_AVAILABLE: ' + reason + '\n', encoding='utf-8')
        return result
    executable = shutil.which(command[0])
    if executable is None and command[0] != sys.executable:
        result['status'] = 'TOOL_ERROR'
        result['reason'] = 'Required executable is not installed'
        (output / f'{name}.log').write_text(result['reason'] + '\n', encoding='utf-8')
        return result
    started = time.monotonic()
    try:
        code, log = asyncio.run(execute(command, cwd, timeout, name, output))
        result['status'] = 'PASS' if code == 0 else 'FAIL'
        result['exit_code'] = code
    except TimeoutError:
        result['status'] = 'TOOL_ERROR'
        result['reason'] = f'timeout after {timeout} seconds'
        log = result['reason']
    except OSError as exc:
        result['status'] = 'TOOL_ERROR'
        result['reason'] = type(exc).__name__
        log = str(exc)
    result['duration_sec'] = round(time.monotonic() - started, 2)
    log = SENSITIVE.sub(lambda m: m.group(1) + '=***REDACTED***', log)
    if len(log) > 500000:
        log = log[:250000] + '\n[TRUNCATED: consult original CI output]\n' + log[-250000:]
    (output / f'{name}.log').write_text(log + '\n', encoding='utf-8')
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('prebuild', 'postbuild'), required=True)
    parser.add_argument('--frontend', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--logs', type=Path, required=True)
    args = parser.parse_args()
    frontend = args.frontend.resolve()
    repo = args.repo.resolve()
    logs = args.logs.resolve()
    logs.mkdir(parents=True, exist_ok=True)
    if not frontend.is_dir():
        raise SystemExit('Frontend build directory absent: cannot collect diagnostics')
    results = []

    def run(name, command, cwd=frontend, timeout=180, reason=''):
        row = check(name, command, cwd, logs, timeout, reason)
        results.append(row)
        print('EFHC_QUALITY_CHECK=' + json.dumps(row, ensure_ascii=False, sort_keys=True), flush=True)

    backend = next((p for p in (repo / 'site/backend', repo / 'site/ci/backend', repo / 'backend')
                    if (p / 'app').is_dir()), None)
    tools = repo / 'deployment/pages-tools'
    if not tools.is_dir():
        tools = repo / 'frontend/src/reconstruction'
    support = frontend / 'src/reconstruction/pages_ci'
    if args.phase == 'prebuild':
        run('frontend-typecheck', ['npm', 'run', 'typecheck'], timeout=240)
        public_suite = repo / 'tests/frontend/reconstruction/tonconnect-public.test.mjs'
        run('frontend-tonconnect-public-regression',
            ['node', '--test', str(public_suite)] if public_suite.is_file() else None,
            timeout=240, reason='Public TONConnect source guard is missing')
        run('frontend-tonconnect-private-acceptance', None,
            reason='Private TONConnect updater/ops/workflow acceptance suite is outside public Pages import')
        run('npm-dependency-audit', ['npm', 'audit', '--audit-level=high', '--json'], timeout=150)
        pyfiles = sorted(str(p) for p in tools.glob('*.py'))
        scanner = frontend / 'src/reconstruction/ci_predeploy_diagnostics.py'
        if scanner.is_file():
            pyfiles.append(str(scanner))
        if not pyfiles:
            pyfiles = [str(Path(__file__).resolve())]
        pyfiles = list(dict.fromkeys(pyfiles))
        run('pages-python-compile', [sys.executable, '-m', 'py_compile', *pyfiles], cwd=repo)
        for name, cmd in (
            ('pages-flake8', ['flake8', '--isolated', '--max-line-length=120', *pyfiles]),
            ('pages-bandit', ['bandit', '-q', *pyfiles]),
            ('pages-ruff', ['ruff', 'check', '--isolated', *pyfiles]),
        ):
            run(name, cmd, cwd=repo, timeout=120)
        if backend is None:
            for name in (
                'backend-compile', 'backend-bandit', 'backend-flake8', 'backend-ruff',
                'backend-mypy', 'backend-pip-audit', 'backend-pytest',
            ):
                run(name, None, cwd=repo,
                    reason='Private backend/tests are absent from public Test-3 ZIP importer; use FULL private CI')
        else:
            app = backend / 'app'
            run('backend-compile', [sys.executable, '-m', 'compileall', '-q', str(app)], cwd=repo)
            run('backend-bandit', ['bandit', '-q', '-r', str(app)], cwd=repo, timeout=180)
            run('backend-flake8', ['flake8', '--isolated', '--max-line-length=120', str(app)],
                cwd=repo, timeout=180)
            run('backend-ruff', ['ruff', 'check', str(app)], cwd=repo, timeout=180)
            run('backend-mypy', ['mypy', '--no-incremental', str(app)], cwd=repo, timeout=240)
            lock = backend / 'requirements.lock'
            run('backend-pip-audit',
                ['pip-audit', '-r', str(lock), '--disable-pip', '--no-deps', '--strict']
                if lock.exists() else None, cwd=repo, timeout=240,
                reason='backend/requirements.lock missing')
            tests = next((p for p in (repo / 'site/tests', repo / 'tests') if p.is_dir()), None)
            run('backend-pytest', [sys.executable, '-m', 'pytest', '-q', str(tests)] if tests else None,
                cwd=repo, timeout=360, reason='Backend tests absent; no integration qualification')
    else:
        for name, filename in (
            ('frontend-performance-budgets', 'budgets.mjs'),
            ('frontend-release-assets', 'verify-production-assets.mjs'),
        ):
            script = support / filename
            run(name, ['node', str(script)] if script.is_file() else None,
                reason=f'Real Pages checker absent: {filename}')
    data = {
        'schema': SCHEMA, 'phase': args.phase, 'backend_source_present': backend is not None,
        'checks': results,
        'totals': {status: sum(row['status'] == status for row in results)
                   for status in ('PASS', 'FAIL', 'TOOL_ERROR', 'NOT_AVAILABLE')},
    }
    (logs / f'quality-{args.phase}.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8',
    )
    print('EFHC_QUALITY_PHASE_SUMMARY=' + json.dumps(data['totals'], sort_keys=True))
    return 1 if any(row['status'] in ('FAIL', 'TOOL_ERROR') for row in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
