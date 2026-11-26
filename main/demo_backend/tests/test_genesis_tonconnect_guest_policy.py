"""Strict, TEST-only TON Proof wallet route policy. No mainnet or Neon writes."""
from __future__ import annotations

import unittest
import ast
from pathlib import Path
from types import SimpleNamespace

from demo_backend.tonconnect import (
    demo_proof_subject,
    genesis_guest_wallet_route,
)


class GenesisGuestTonConnectPolicyTests(unittest.TestCase):
    def test_only_exact_verified_proof_routes_are_exposed(self):
        self.assertEqual(
            genesis_guest_wallet_route("GET", "/api/wallets/tonconnect/proof-payload"),
            "read",
        )
        self.assertEqual(
            genesis_guest_wallet_route("POST", "/api/wallets/tonconnect/check-proof"),
            "write",
        )
        self.assertEqual(
            genesis_guest_wallet_route("POST", "/api/wallets/connect"),
            "write",
        )
        self.assertEqual(genesis_guest_wallet_route("POST", "/api/wallets/123/make-primary"), "write")
        self.assertEqual(genesis_guest_wallet_route("DELETE", "/api/wallets/123"), "write")
        for method, path in (
            ("DELETE", "/api/wallets/0"),
            ("POST", "/api/wallets/abc/make-primary"),
            ("DELETE", "/api/wallets/123/anything"),
            ("POST", "/api/wallets/tonconnect/proof-payload"),
            ("GET", "/api/wallets/tonconnect/check-proof"),
            ("GET", "/api/wallets/connect"),
            ("POST", "/api/wallets/make-primary"),
            ("POST", "/api/withdraw/request"),
            ("POST", "/api/admin/withdrawals"),
            ("POST", "/api/wallets/connect/"),
            ("OPTIONS", "/api/wallets/connect"),
            ("PUT", "/api/wallets/connect"),
        ):
            with self.subTest(method=method, path=path):
                self.assertIsNone(genesis_guest_wallet_route(method, path))

    def test_synthetic_subject_is_not_a_telegram_identity_or_owner_selector(self):
        a = demo_proof_subject("0000003001")
        b = demo_proof_subject("0000003002")
        self.assertNotEqual(a, b)
        self.assertGreater(a, 4_000_000_000_000)
        for value in ("0000000000", "000000008", "insecure", "12345678901"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    demo_proof_subject(value)


    def test_direct_deposit_metadata_get_is_exactly_scoped(self):
        demo_root = Path(__file__).resolve().parents[1]
        app_root = Path(__file__).resolve().parents[2]
        asgi_tree = ast.parse((demo_root / "asgi.py").read_text(encoding="utf8"))
        deposit_tree = ast.parse(
            (app_root / "backend/app/routes/deposit_routes.py").read_text(encoding="utf8")
        )
        direct_open = next(
            node for node in deposit_tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "open_direct_deposit"
        )
        verbs = {
            decorator.func.attr.upper()
            for decorator in direct_open.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "router"
        }
        self.assertEqual(verbs, {"GET", "POST"})

        def assigned(name):
            return next(
                node.value for node in ast.walk(asgi_tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name
                        for target in node.targets)
            )

        prefixes = ast.literal_eval(assigned("safe_get_prefixes"))
        safe_get = ast.Expression(body=assigned("safe_get"))
        ast.fix_missing_locations(safe_get)
        expression = compile(safe_get, "demo_backend/asgi.py", "eval")

        def allowed(method, path, scope):
            namespace = {
                "any": any,
                "method": method,
                "path": path,
                "operator_session": SimpleNamespace(scope=scope),
                "safe_get_prefixes": prefixes,
                "guest_ton_route": None,
                "visual_aggregate": False,
            }
            return bool(eval(expression, namespace, namespace))

        self.assertTrue(allowed("GET", "/api/deposit/direct-open", "guest"))
        self.assertTrue(allowed("HEAD", "/api/deposit/direct-open", "guest"))
        for route in ("/api/user/me/panels-summary", "/api/withdraw/list"):
            self.assertTrue(allowed("GET", route, "guest"))
            self.assertTrue(allowed("HEAD", route, "guest"))
            self.assertFalse(allowed("GET", route, "visual"))
            self.assertFalse(allowed("POST", route, "guest"))

        for method, path, scope in (
            ("POST", "/api/deposit/direct-open", "guest"),
            ("PUT", "/api/deposit/direct-open", "guest"),
            ("GET", "/api/deposit/packages", "guest"),
            ("GET", "/api/deposit/efhc", "guest"),
            ("GET", "/api/deposit/direct-open", "visual"),
            ("GET", "/api/admin", "guest"),
        ):
            with self.subTest(method=method, path=path, scope=scope):
                self.assertFalse(allowed(method, path, scope))


if __name__ == "__main__":
    unittest.main()
