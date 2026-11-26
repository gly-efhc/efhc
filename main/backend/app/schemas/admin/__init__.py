from __future__ import annotations

import app.schemas.admin.admin_schemas as _target

__all__ = [
    "AdminActor",
    "AdminBurnIn",
    "AdminBurnOut",
    "AdminEmitIn",
    "AdminEmitOut",
    "AdminForceCreditUserFromBankIn",
    "AdminForceCreditUserFromBankOut",
    "AdminForceDebitUserToBankIn",
    "AdminForceDebitUserToBankOut",
    "AdminNftRequestModerateIn",
    "AdminNftRequestModerateOut",
    "AdminReportsOut",
    "AdminReportsQueryIn",
    "AdminShopItemOut",
    "AdminShopItemUpsertIn",
    "AdminTaskOut",
    "AdminTaskUpsertIn",
    "AdminTonReconcileIn",
    "AdminTonReconcileOut",
    "AdminWithdrawModerateIn",
    "AdminWithdrawModerateOut",
    "ModerationAction",
    "ShopItemType",
    "TaskType",
    "TonInboxLogRow",
    "TonInboxPage",
    "WithdrawPage",
    "WithdrawRow",
]

for _name in __all__:
    globals()[_name] = getattr(_target, _name)
