import hashlib
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from efhc_import_full import REQUIRED, pathname, run


def make_archive(path, *, extra=None, wrong_file=False):
    files = {p: b"synthetic import fixture\n" for p in REQUIRED}
    manifest = {
        "format": "efhc-full-import",
        "schema": 1,
        "target": "gly-efhc/efhc",
        "base": "0" * 40,
        "files": [
            {"path": p, "size": len(data), "mode": "100644", "sha256": hashlib.sha256(data).hexdigest()}
            for p, data in sorted(files.items())
        ],
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("IMPORT.md", "Test only\n")
        archive.writestr("ROUTES.json", json.dumps({"pages": ["/"], "api": {"/health": ["GET"]}}))
        for idx, (p, data) in enumerate(sorted(files.items())):
            archive.writestr("payload/" + p, b"changed" if wrong_file and idx == 0 else data)
        if extra:
            archive.writestr(extra, "not in manifest")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refused(f, message):
    try:
        f()
    except ValueError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError("Expected refusal: " + message)


def main():
    refused(lambda: pathname("demo_backend/asgi.py"), "not in import scope")
    pathname("main/demo_backend/docker-compose.demo.yml")
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        root = folder / "checkout"
        root.mkdir()
        bundle = folder / "fixture.zip"
        sha = make_archive(bundle)
        base, count, pending = run(root, bundle, sha, False)
        assert not list(root.iterdir()) and count == len(REQUIRED) == pending
        assert run(root, bundle, sha, True) == (base, count, count)
        assert run(root, bundle, sha, False) == (base, count, 0)
        changed = root / "site/frontend/package-lock.json"
        changed.write_bytes(b"owner content")
        refused(lambda: run(root, bundle, sha, True), "refusing to overwrite")
        assert changed.read_bytes() == b"owner content"
        refused(lambda: run(root, bundle, "0" * 64, True), "SHA-256 mismatch")
        for attack in ("payload/../../outside", "payload/.github/workflows/untrusted.yml"):
            sha = make_archive(bundle, extra=attack)
            refused(lambda: run(root, bundle, sha, True), "ZIP content differs from manifest")
        sha = make_archive(bundle, wrong_file=True)
        refused(lambda: run(root, bundle, sha, True), "checksum mismatch")
        assert not (folder / "outside").exists()
    print("EFHC_FULL_IMPORT_CONTRACT=PASS")


if __name__ == "__main__":
    main()
