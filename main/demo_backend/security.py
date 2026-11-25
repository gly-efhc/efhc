"""DEMO external integration routing policy.

The operator explicitly requires real TonConnect/TON Proof/provider callbacks.
This module therefore does NOT shadow, stub, or reject their HTTP routes.
The hard boundary is instead at the process configuration: Neon TEST DSN,
no production real-funds flag, and no embedded on-chain payout agent.
Business authorization, cryptographic proof, replay and idempotency remain
those of the unmodified FastAPI backend.
"""
from __future__ import annotations


def is_external_blocked(method: str, path: str) -> bool:
    """Existing HTTP integrations are routed to the canonical backend.

    Intentionally no route-level external-integration denylist. The DEMO
    executable explicitly prevents starting the automatic funds-sending
    process; any separately deployed production worker is out of scope.
    """
    return False
