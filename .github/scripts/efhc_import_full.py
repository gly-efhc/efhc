#!/usr/bin/env python3
"""Validate an EFHC full import, optionally add it to a clean checkout."""
import argparse
import hashlib
import json
import re
import stat
from pathlib import Path
from zipfile import ZipFile

SHA = re.compile(r"[0-9a-f]{64}\Z")
GIT = re.compile(r"[0-9a-f]{40}\Z")
PATH = re.compile(r"[A-Za-z0-9._ ()-]+(?:/[A-Za-z0-9._ ()-]+)*\Z")
PREFIX = (
    "site/frontend/", "site/ci/",
    "main/backend/app/", "main/backend/migrations/", "main/backend/openapi/",
    "main/demo_backend/", "main/contracts/", "main/tests/efhc_backend/",
    "main/tests/integration/", "main/ops/routes/",
)
FIXED = {
    "AGENTS.md", "INDEX.md", "KERNEL.md", "LICENSE.txt", "README.md", "START_HERE.md",
    "import/README.md", "site/APPLICATION_RULES.md", "site/EFHC_APPLICATION_RULES.md",
    "site/RECOVERY.md", "site/RELEASE.json", "main/.dockerignore", "main/.env.example",
    "main/VERSION", "main/pytest.ini", "main/pyproject.toml",
    "main/requirements.txt", "main/requirements-dev.txt", "main/requirements-test.txt",
    "main/backend/README_ADMIN_GLOBAL_IDS.md", "main/backend/__init__.py",
    "main/backend/alembic.ini", "main/backend/init.py", "main/backend/run.py",
    "main/backend/requirements.lock", "main/backend/requirements.txt", "main/tests/conftest.py",
}
REQUIRED = {
    "site/frontend/package-lock.json", "site/frontend/src/pages/index.tsx",
    "site/ci/pages-tools/prepare_pages.py", "site/RELEASE.json",
    "main/backend/app/main.py", "main/demo_backend/asgi.py",
    "main/demo_backend/Dockerfile", "main/backend/requirements.lock",
    "main/backend/migrations/versions/0001_initial_release_schema.py",
    "main/backend/openapi/openapi.json",
}
CAP = 50 * 1024 * 1024
BLOCK = {".git", ".github", "node_modules", "__pycache__", ".next", "secrets", ".aws"}

def check(ok, message):
    if not ok:
        raise ValueError(message)

def pathname(p):
    check(isinstance(p, str) and PATH.fullmatch(p), f"invalid name: {p!r}")
    parts = p.split("/")
    check(not any(x in {".", ".."} or x.lower() in BLOCK or x != x.strip() or x.endswith(".") for x in parts), f"unsafe path: {p}")
    check(not any(x.lower().startswith(".env") for x in parts) or p=="main/.env.example", f"environment file: {p}")
    check(p=="main/demo_backend/docker-compose.demo.yml" or Path(p).suffix.lower() not in {".zip", ".tar", ".gz", ".db", ".sqlite", ".pem", ".key", ".pfx", ".p12", ".yml", ".yaml"}, f"blocked file type: {p}")
    check(p in FIXED or p.startswith(PREFIX), f"not in import scope: {p}")

def run(root, bundle, expected, apply):
    check(SHA.fullmatch(expected), "expected whole ZIP SHA-256")
    check(bundle.is_file() and not bundle.is_symlink() and bundle.stat().st_size<=CAP, "bad ZIP size or type")
    with bundle.open("rb") as stream:
        check(hashlib.file_digest(stream,"sha256").hexdigest()==expected, "ZIP SHA-256 mismatch")
    with ZipFile(bundle) as z:
        entries=z.infolist()
        check(len(entries)<=5000 and sum(x.file_size for x in entries)<=3*CAP,"uncompressed scope too large")
        names=[x.filename for x in entries]
        check(len({n.casefold() for n in names})==len(names),"duplicate ZIP name")
        check("manifest.json" in names,"no manifest")
        for entry in entries:
            mode=entry.external_attr>>16
            check(not entry.is_dir() and stat.S_IFMT(mode) in (0,stat.S_IFREG) and not entry.flag_bits&1 and entry.file_size<=CAP, "unsafe ZIP member")
        m=json.loads(z.read("manifest.json"))
        check(m["format"]=="efhc-full-import" and m["schema"]==1 and m["target"]=="gly-efhc/efhc" and GIT.fullmatch(m["base"]), "wrong import contract")
        paths={}
        for row in m["files"]:
            p=row["path"]
            pathname(p)
            check(p not in paths and SHA.fullmatch(row["sha256"]) and row["mode"] in ("100644","100755"),"malformed manifest")
            paths[p]=row
        check(REQUIRED<=paths.keys(),"required frontend/backend/routes missing")
        prefixes={q for p in paths for q in [p.rpartition("/")[0]] if q}
        check(all("/".join(p.split("/")[:i]) not in paths for p in prefixes for i in range(1,len(p.split("/"))+1)),"file used as a directory")
        docs={"manifest.json","IMPORT.md","ROUTES.json"}
        check(set(names)==docs|{"payload/"+p for p in paths},"ZIP content differs from manifest")
        pending=[]
        for p,row in paths.items():
            data=z.read("payload/"+p)
            check(hashlib.sha256(data).hexdigest()==row["sha256"] and len(data)==row["size"],f"checksum mismatch: {p}")
            target=root/p
            check(not any(x.is_symlink() for x in (target,*[q for q in target.parents if q!=root and root in q.parents])),f"symlink in target: {p}")
            left=[q for q in target.parents if q!=root and root in q.parents]
            check(all(not q.exists() or q.is_dir() for q in left), f"file in directory position: {p}")
            if target.exists():
                actual = target.read_bytes() if target.is_file() else None
                check(actual==data, f"refusing to overwrite different content: {p}")
                check(bool(target.stat().st_mode&stat.S_IXUSR)==(row["mode"]=="100755"),f"executable mode differs: {p}")
            else:
                pending.append((target,row["mode"],data))
        route_map=json.loads(z.read("ROUTES.json"))
        check(route_map["api"] and route_map["pages"], "missing route inventory")
        check(len(route_map["pages"])==len(set(route_map["pages"])),"ambiguous page inventory")
        if apply:
            for p,mode,data in pending:
                p.parent.mkdir(parents=True,exist_ok=True)
                with p.open("xb") as fp:
                    fp.write(data)
                p.chmod(0o755 if mode=="100755" else 0o644)
        return m["base"],len(paths),len(pending)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("zip",type=Path)
    a.add_argument("sha256")
    a.add_argument("--root",required=True,type=Path)
    a.add_argument("--apply",action="store_true",help="add files after complete validation; never overwrite")
    q=a.parse_args()
    try:
        base,count,pending=run(q.root.resolve(),q.zip,q.sha256,q.apply)
    except (ValueError, KeyError, TypeError, OSError) as e:
        a.exit(1,f"EFHC_IMPORT_REFUSED: {e}\n")
    print(f"EFHC_FULL_IMPORT={'APPLIED' if q.apply else 'DRY_RUN'} base={base} files={count} new={pending}")
