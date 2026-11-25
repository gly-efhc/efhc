"""Fail-closed real TON testnet safeguards, without external requests."""
from __future__ import annotations

import unittest

from demo_backend.config import DemoConfig, DemoConfigurationError
from demo_backend.testnet_policy import (
    DemoTestnetPolicyError,
    TESTNET_CHAIN_ID,
    require_testnet_wallet_chain,
    verified_testnet_target,
)

_TESTNET = {
    "DEMO_DATASET": "genesis",
    "TON_NETWORK": "testnet",
    "TON_API_BASE_URL": "https://testnet.tonapi.io",
    "ALLOW_REAL_FUNDS": "false",
    "RUN_EMBEDDED_TON_AGENT": "false",
}

_HOST = "ep-weathered-heart-zak4zgp6.c-2.eu-west-2.aws.neon.tech"
_DSN = f"postgresql://test-user:nonsecret@{_HOST}/neondb?sslmode=require"


class TestnetPolicyTests(unittest.TestCase):
    def test_expected_chain_and_official_testnet_endpoint(self):
        t=verified_testnet_target(dict(_TESTNET))
        self.assertEqual(t.chain_id,"-3")
        self.assertEqual(t.network,"testnet")
        self.assertEqual(t.tonapi_base_url,"https://testnet.tonapi.io")
        self.assertEqual(require_testnet_wallet_chain(TESTNET_CHAIN_ID),"-3")

    def test_mainnet_wallet_and_missing_chain_denied(self):
        for chain in ("-239","mainnet","testnet",None,"",3):
            with self.subTest(chain=chain):
                with self.assertRaises(DemoTestnetPolicyError):
                    require_testnet_wallet_chain(chain)

    def test_mainnet_config_denied(self):
        for val in ("mainnet","-239","", "TEST"):
            with self.subTest(network=val):
                with self.assertRaises(DemoTestnetPolicyError):
                    verified_testnet_target({**_TESTNET,"TON_NETWORK":val})

    def test_mainnet_rpc_and_unknown_hosts_denied(self):
        bad_urls=(
            "https://tonapi.io",
            "https://tonapi.io/v2",
            "http://testnet.tonapi.io",
            "https://testnet.tonapi.io.evil.example",
            "https://testnet.tonapi.io@evil.example",
            "https://testnet.tonapi.io/path",
            "https://testnet.tonapi.io/?wallet=1",
            "",
        )
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(DemoTestnetPolicyError):
                    verified_testnet_target({**_TESTNET,"TON_API_BASE_URL":url})

    def test_real_funds_agent_and_non_genesis_denied(self):
        for patch in (
            {"ALLOW_REAL_FUNDS":"true"},
            {"ALLOW_REAL_FUNDS":"1"},
            {"RUN_EMBEDDED_TON_AGENT":"yes"},
            {"DEMO_DATASET":"legacy"},
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(DemoTestnetPolicyError):
                    verified_testnet_target({**_TESTNET,**patch})

    def test_demo_config_requires_testnet_when_real_integration_enabled(self):
        env={
            **_TESTNET,
            "EFHC_DEMO_REAL_TESTNET":"1",
            "EFHC_DEMO_ENABLED":"1",
            "ENV":"local",
            "DEMO_DATABASE_URL":_DSN,
            "DATABASE_URL":_DSN,
            "DEMO_NEON_HOST":_HOST,
            "DEMO_OPERATOR_PASSWORD":"dummy-operator-only-test-password",
            "DEMO_INITIAL_GLOBAL_ID":"0000003001",
        }
        self.assertTrue(DemoConfig.from_env(env).testnet_integrations_enabled)
        with self.assertRaises(DemoConfigurationError):
            DemoConfig.from_env({**env,"TON_NETWORK":"mainnet"})
        with self.assertRaises(DemoConfigurationError):
            DemoConfig.from_env({**env,"TON_API_BASE_URL":"https://tonapi.io"})


if __name__ == "__main__":
    unittest.main()
