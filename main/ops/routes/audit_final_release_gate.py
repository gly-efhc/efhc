from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPTS = [
    [
        sys.executable,
        str(ROOT / "ops/frontend/audit_blitz_bundle_cleanup.py"),
    ],
    [sys.executable, str(ROOT / "ops/i18n/audit_locale_coverage.py")],
    [
        sys.executable,
        str(ROOT / "ops/routes/audit_shop_payment__path__coverage.py"),
    ],
    [
        sys.executable,
        str(ROOT / "ops/routes/audit_shop_payments_compliance.py"),
    ],
    [
        sys.executable,
        str(ROOT / "ops/routes/audit_external_payment_flow_e2e.py"),
    ],
    [
        sys.executable,
        str(ROOT / "ops/routes/audit_withdraw_blitz_compat.py"),
    ],
    [
        sys.executable,
        str(ROOT / "ops/routes/audit_legacy_shop_read_only.py"),
    ],
    [
        sys.executable,
        str(
            ROOT / "ops/routes/audit_blitz_limits_and_openapi_freeze.py"
        ),
    ],
]

results = []
failed = False
for cmd in SCRIPTS:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    ok = proc.returncode == 0
    results.append(
        {
            "script": str(Path(cmd[-1]).relative_to(ROOT)),
            "ok": ok,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    )
    if not ok:
        failed = True

print(
    json.dumps(
        {"ok": not failed, "results": results},
        ensure_ascii=False,
        indent=2,
    )
)
if failed:
    raise SystemExit(1)
