import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
BROWSER_INSTALL = re.compile(r"\bnpm\s+install\b[^\r\n]*\bplaywright-core(?P<spec>@[^\s|\"']+)?[^\r\n]*")
FRONTEND_LOCK = ROOT / "frontend/package-lock.json"


class CiVersionPolicyTests(unittest.TestCase):
    def test_all_standalone_node_browser_installs_follow_the_stable_channel(self):
        counts = {}
        for workflow in WORKFLOWS.glob("*.yml"):
            installs = list(BROWSER_INSTALL.finditer(workflow.read_text(encoding="utf-8")))
            if not installs:
                continue
            counts[workflow.name] = len(installs)
            for install in installs:
                with self.subTest(workflow=workflow.name):
                    self.assertEqual(install["spec"], "@latest")
                    self.assertIn("--ignore-scripts", install[0])
        self.assertTrue({"efhc-pages.yml", "efhc-parity.yml", "efhc-preview-smoke.yml"} <= counts.keys())

    def test_shop_browser_version_is_resolved_apart_from_application_lock(self):
        path = WORKFLOWS / "shop-native.yml"
        if not path.is_file():
            return
        content = path.read_text(encoding="utf-8")
        self.assertRegex(content, r"\bruns-on:\s*ubuntu-26\.04\b")
        self.assertRegex(content, r"\bvenv\b[^\r\n]*shop-browser")
        self.assertRegex(content, r"\bpip --isolated install\b[^\r\n]*--upgrade playwright(?:\s|$)")
        self.assertRegex(content, r"(?<!\S)-m playwright install --with-deps chromium\b")
        self.assertRegex(content, r"(?<!\S)-m playwright --version\b")
        self.assertNotRegex(content, r"\bplaywright(?:==|~=|>=|<=|!=|<|>)")

    def test_frontend_build_uses_the_application_lock(self):
        lock = json.loads(FRONTEND_LOCK.read_text(encoding="utf-8"))
        self.assertGreaterEqual(lock["lockfileVersion"], 2)
        for name in ("efhc-pages.yml", "efhc-parity.yml"):
            with self.subTest(workflow=name):
                content = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertRegex(content, r"\bnpm\s+ci(?:\s|$)")
                self.assertNotRegex(content, r"\bnpm\s+(?:update|upgrade)(?:\s|$)")


if __name__ == "__main__":
    unittest.main()
