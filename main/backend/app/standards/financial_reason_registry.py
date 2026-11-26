"""Канонический реестр денежных reason для отчётности EFHC-проводок."""

TASK_BONUS_REASON_PREFIX = "task_bonus:"
REFERRAL_ACTIVE_UNIT_REASON = "referral_active_unit"
REFERRAL_LEVEL_BONUS_REASON = "referral_level_bonus"
REFERRAL_BONUS_REASONS = (
    REFERRAL_ACTIVE_UNIT_REASON,
    REFERRAL_LEVEL_BONUS_REASON,
)

__all__ = [
    "TASK_BONUS_REASON_PREFIX",
    "REFERRAL_ACTIVE_UNIT_REASON",
    "REFERRAL_LEVEL_BONUS_REASON",
    "REFERRAL_BONUS_REASONS",
]
