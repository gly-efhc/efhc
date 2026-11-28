"""One blockchain transaction identity across hex/base64 provider encodings."""

from __future__ import annotations

import base64
import binascii
import re
from contextlib import suppress


def tx_hash_identity(value: str) -> tuple[str, list[str], str | None]:
    raw = str(value or "").strip()
    decoded: bytes | None = None
    if re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        decoded = bytes.fromhex(raw)
    elif re.fullmatch(r"[A-Za-z0-9+/_-]{43}=?", raw):
        with suppress(ValueError, binascii.Error):
            decoded = base64.b64decode(
                raw + "=" * (-len(raw) % 4), altchars=b"-_",
                validate=True,
            )
    if decoded is None or len(decoded) != 32:
        # Preserve opaque historical/internal IDs; provider intake is strict.
        return raw, [raw], None
    canonical = decoded.hex()
    encoded = base64.b64encode(decoded).decode()
    url_encoded = base64.urlsafe_b64encode(decoded).decode()
    aliases = sorted({raw, canonical, canonical.upper(), encoded, encoded
                      .rstrip("="), url_encoded, url_encoded.rstrip("=")})
    return canonical, aliases, canonical
