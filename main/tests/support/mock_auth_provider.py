"""Test-only mock adapter для доказательства registry цикла 1609."""

from __future__ import annotations

from app.identity import AuthProvider


class MockAuthProviderAdapter:
    """Проверяет только явный test envelope без side effects."""

    provider = AuthProvider.MOCK

    def verify_subject(self, raw_input: object) -> str | None:
        """Вернуть subject только после явного test verification."""

        if not isinstance(raw_input, dict):
            return None
        if raw_input.get("test_verification") is not True:
            return None
        subject = raw_input.get("subject")
        return subject if isinstance(subject, str) else None
