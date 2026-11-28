"""Provider-specific canonical TON wallet-id resolver цикла 1615."""

from __future__ import annotations

from dataclasses import dataclass

from app.lib.ton_address import TonAddressError, parse_ton_address


class TonWalletIdResolutionError(ValueError):
    """TON provider subject не может быть определён однозначно."""

    code = "auth.ton_wallet_id_invalid"
    message = "TON-адрес недействителен"

    def __init__(self, reason: str = "ADDRESS_INVALID") -> None:
        self.reason = reason
        super().__init__(self.message)

    def as_dict(self) -> dict[str, str]:
        """Вернуть безопасный payload без исходного адреса."""

        return {
            "код": self.code,
            "сообщение": self.message,
            "причина": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CanonicalTonWalletId:
    """Канонический TON provider subject.

    Результат предназначен для будущего IdentityResolver.
    """

    raw: str
    workchain: int
    account_id_hex: str

    @property
    def ton_wallet_id(self) -> str:
        """Вернуть канонический ``ton_wallet_id`` — адрес TON-кошелька."""

        return self.raw

    def __repr__(self) -> str:
        return (
            "CanonicalTonWalletId("
            f"workchain={self.workchain!r}, "
            "account_id_hex='<redacted>')"
        )


class CanonicalTonWalletIdResolver:
    """Преобразовать допустимые TON-адреса в единый ``ton_wallet_id``."""

    def resolve(self, value: object) -> CanonicalTonWalletId:
        try:
            parsed = parse_ton_address(value)
        except TonAddressError as exc:
            reason = str(exc) or "ADDRESS_INVALID"
            raise TonWalletIdResolutionError(reason) from exc
        return CanonicalTonWalletId(
            raw=parsed.raw,
            workchain=parsed.workchain,
            account_id_hex=parsed.account_id_hex,
        )


def resolve_canonical_ton_wallet_id(value: object) -> CanonicalTonWalletId:
    """Функциональная boundary для canonical TON wallet-id resolution."""

    return CanonicalTonWalletIdResolver().resolve(value)


__all__ = [
    "CanonicalTonWalletId",
    "CanonicalTonWalletIdResolver",
    "TonWalletIdResolutionError",
    "resolve_canonical_ton_wallet_id",
]
