"""Test-only реализация интерфейса IdentityResolver цикла 1610."""

from __future__ import annotations

from app.identity import (
    IdentityResolution,
    IdentityResolver,
    VerifiedIdentity,
)


class MockIdentityResolver:
    """Детерминированный resolver без БД, create и session effects."""

    def __init__(self, result: IdentityResolution) -> None:
        self._result = result
        self.received: list[VerifiedIdentity] = []

    async def resolve_verified_identity(
        self,
        identity: VerifiedIdentity,
    ) -> IdentityResolution:
        """Принять только verified result и вернуть заданный outcome."""

        if not isinstance(identity, VerifiedIdentity):
            raise TypeError("Требуется VerifiedIdentity")
        self.received.append(identity)
        return self._result


assert isinstance(MockIdentityResolver, type)
assert IdentityResolver is not None
