from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

TOOLS = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("prepare_pages", TOOLS / "prepare_pages.py")
prepare = module_from_spec(spec)
spec.loader.exec_module(prepare)


class WalletLayoutTest(unittest.TestCase):
    def test_mount_only_applies_to_build_copy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "site/frontend"
            source_dir = source / "src/components/profile"
            target = root / "output"
            target_dir = target / "src/components/profile"
            template_dir = root / "site/ci/pages-tools"
            for p in (source_dir, target_dir, template_dir):
                p.mkdir(parents=True)
            template = (TOOLS / "wallet-layout.tsx").read_text()
            (template_dir / "wallet-layout.tsx").write_text(template)
            anchor = '      <div className="standalone-wallet-layout">'
            for p in (source_dir, target_dir):
                (p / "ProfileWalletSection.tsx").write_text(anchor)
            prepare.install_genesis_wallet_layout(source, target)
            self.assertEqual((source_dir / "ProfileWalletSection.tsx").read_text(), anchor)
            self.assertFalse((source_dir / "TestWalletLayout.tsx").exists())
            self.assertIn("<TestWalletLayout />", (target_dir / "ProfileWalletSection.tsx").read_text())
            self.assertEqual((target_dir / "TestWalletLayout.tsx").read_text(), template)

    def test_fixture_never_maps_to_transaction_wallet(self):
        template = (TOOLS / "wallet-layout.tsx").read_text()
        for required in ("isDemoBackendMode()", "getAuthAuthorizationHeader() === authorization",
                         '"/staging/wallet-layout", "GET"', "rows.length !== 3",
                         'response.headers.get("X-EFHC-Data-Source") === "neon-test"'):
            self.assertIn(required, template)
        for forbidden in ("proof_verified", "wallet_address:", "onClick", "wallet_bindings", "setQueryData"):
            self.assertNotIn(forbidden, template)
