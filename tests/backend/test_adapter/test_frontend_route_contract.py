"""Every API route referenced by EFHC frontend must exist in the real FastAPI app.

This is a static source/OpenAPI-boundary test, not a live Neon integration test.
Frontend routes, canonical backend routers and test control routes remain shared;
we must never silently replace a deleted browser DEMO route with a fake JSON.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_frontend_routes_are_all_registered_on_demo_backend():
    root = Path(__file__).resolve().parents[3]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DEMO_DATASET": "legacy",
        "PYTHONPATH": f"{root}:{root / 'backend'}:{root / 'environments/test'}",
        "EFHC_DEMO_ENABLED": "1",
        "DEMO_DATABASE_URL": "postgresql+asyncpg://efhc_test:fake@ep-fragrant-feather-zaribpm5.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require",
        "DEMO_NEON_HOST": "ep-fragrant-feather-zaribpm5.c-2.eu-west-2.aws.neon.tech",
        "DEMO_OPERATOR_PASSWORD": "smoke-only-password-unique-0123456789",
        "DEMO_INITIAL_GLOBAL_ID": "0000000002",
        "SECRET_KEY": "EFHC-test-only-secret-key-0123456789",
        "ENV": "local",
        "ALLOW_REAL_FUNDS": "false",
        "RUN_EMBEDDED_TON_AGENT": "false",
    }
    script = r'''
import pathlib,re
from fastapi.routing import APIRoute
from demo_backend.asgi import app
root=pathlib.Path.cwd()/"frontend/src"
generated=root/"lib/api/generated"
paths={}
for f in generated.glob("*.ts"):
    text=f.read_text()
    paths.update(re.findall(r'export\s+const\s+([A-Z0-9_]+)\s*=\s*["\'](\/[A-Za-z0-9_{}\-./]+)["\']', text, re.S))
for f in generated.glob("*.ts"):
    for name,target in re.findall(r'export\s+const\s+([A-Z0-9_]+)\s*=\s*([A-Z][A-Z0-9_]+)\s*;',f.read_text()):
        if target in paths:paths[name]=paths[target]
called=set()
for folder in ["services","queries","pages","components"]:
    for f in (root/folder).rglob("*"):
        if f.suffix not in (".ts",".tsx"):continue
        content=f.read_text(errors="ignore")
        for name,route in paths.items():
            if name.endswith("_PATH") and re.search(r'\b'+name+r'\b', content):
                called.add(route)
for f in (root/"services").glob("*.ts"):
    content=f.read_text(errors="ignore")
    for route in re.findall(r'["\'`](\/(?:admin|auth|ads|sync|user|wallets|panels|exchange|withdraw|referrals|ranks|hub|shopfront|shop|deposit|tasks|skins|profile)[A-Za-z0-9_./{}$\-]*)',content):
        if not "$" in route:called.add(route)
routes={r.path for r in app.routes if isinstance(r,APIRoute)}
def pattern(route):
    value=route.strip("/").replace(".", r"\.")
    return re.sub(r'\{[^{}]*\}',r'[^/]+',value)
def available(source):
    example=re.sub(r'\{[^{}]*\}',"123",source.split("?")[0].strip("/"))
    return any(re.fullmatch(pattern(route),example) for route in routes)
missing=sorted(x for x in called if x not in ("/admin","/api") and not available("/api"+x) and not available(x))
assert len(routes)>=190,(len(routes),"route regression")
assert len(called)>=100,(len(called),"incomplete frontend route inventory")
assert not missing,"UNMAPPED_FRONTEND_API_ROUTES: "+repr(missing)
print("FRONTEND_BACKEND_ROUTE_COVERAGE_PASS",len(called),len(routes))
'''
    p = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=35,
    )
    assert p.returncode == 0, (p.stdout[-4000:] + "\n" + p.stderr[-4000:])
    assert "FRONTEND_BACKEND_ROUTE_COVERAGE_PASS" in p.stdout
