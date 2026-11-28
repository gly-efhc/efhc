"""TON testnet-only boundary for interactive Genesis TEST integrations.

Real cryptographic TonProof checks remain in the canonical backend.
This gate is intentionally independent from the production TON configuration:
it refuses mainnet, unknown chains, unexpected RPC hosts or live-funds flags.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

TESTNET_CHAIN_ID = "-3"
TONAPI_TESTNET_ORIGIN = "https://testnet.tonapi.io"


class DemoTestnetPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DemoTestnetTarget:
    chain_id: str
    network: str
    tonapi_base_url: str


def require_testnet_wallet_chain(chain: object) -> str:
    if not isinstance(chain, str) or chain != TESTNET_CHAIN_ID:
        raise DemoTestnetPolicyError("TON_TESTNET_WALLET_REQUIRED")
    return chain


def verified_testnet_target(environment: dict[str, str]) -> DemoTestnetTarget:
    if environment.get("DEMO_DATASET", "").strip().lower() != "genesis":
        raise DemoTestnetPolicyError("GENESIS_TEST_ONLY")
    if environment.get("TON_NETWORK", "").strip().lower() != "testnet":
        raise DemoTestnetPolicyError("TON_TESTNET_NETWORK_REQUIRED")
    url = environment.get("TON_API_BASE_URL", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "testnet.tonapi.io"
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
        or url not in {TONAPI_TESTNET_ORIGIN, TONAPI_TESTNET_ORIGIN+"/"}):
        raise DemoTestnetPolicyError("TON_TESTNET_ENDPOINT_REQUIRED")
    if environment.get("ALLOW_REAL_FUNDS", "").strip().lower() in {
        "true", "1", "yes", "on"
    }:
        raise DemoTestnetPolicyError("REAL_FUNDS_FORBIDDEN")
    if environment.get("RUN_EMBEDDED_TON_AGENT", "").strip().lower() in {
        "true", "1", "yes", "on"
    }:
        raise DemoTestnetPolicyError("AUTOMATED_EXTERNAL_SENDER_FORBIDDEN")
    return DemoTestnetTarget(
        chain_id=TESTNET_CHAIN_ID,network="testnet",
        tonapi_base_url=TONAPI_TESTNET_ORIGIN,
    )
