from __future__ import annotations

from typing import Any

from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId


class OutcomeCommentSchema(EfhcBaseModel):
    text: str
    template_key: str | None = None
    source: str
    locale: str
    manual_override_used: bool = False
    auto_translated: bool = False


class OutcomePromoSchema(EfhcBaseModel):
    enabled: bool
    key: str | None = None
    title: str | None = None
    body: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    source: str | None = None


class WithdrawOutcomeBundleSchema(EfhcBaseModel):
    request_id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    outcome_kind: str
    locale: str
    comment: OutcomeCommentSchema
    promo: OutcomePromoSchema | None = None
    top_zone_enabled: bool
    metadata: dict[str, Any] = {}


class WithdrawOutcomePreviewSchema(EfhcBaseModel):
    request_id: ApiLifetimeId
    withdrawal_status: str
    preview_mode: str
    bundle: WithdrawOutcomeBundleSchema
