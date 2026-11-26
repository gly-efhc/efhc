import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ApplicationAliasTests(unittest.TestCase):
    def test_retired_internal_names_are_absent(self):
        scopes = (
            ("main/backend/app", "*.py", re.compile(r"\bShopService\b")),
            ("site/frontend/src", "*.ts*", re.compile(r"\b(?:TonConnectMessage|TonConnectTx|faqRuCatalog)\b")),
        )
        unexpected = []
        for directory, glob, identifiers in scopes:
            for path in (ROOT / directory).rglob(glob):
                if path.is_file():
                    for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if hit := identifiers.search(text):
                            unexpected.append(f"{path.relative_to(ROOT)}:{line}: {hit.group()}")
        self.assertEqual(unexpected, [])

    def test_canonical_shop_and_wallet_types_are_present(self):
        shop = (ROOT / "main/backend/app/services/shop_service.py").read_text(encoding="utf-8")
        ton = (ROOT / "site/frontend/src/lib/ton/tx.ts").read_text(encoding="utf-8")
        self.assertIn("class ShopFacade(ShopContract):", shop)
        self.assertIn("export type TonWalletRawTransaction", ton)
        self.assertIn("export type TonWalletMessage", ton)
