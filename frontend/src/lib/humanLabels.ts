export type TranslationFn = (key: string) => string;

function norm(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

export function taskStatusLabel(
  status: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(status);
  if (!value) return t("tasks.status_ready");
  if (value === "available") return t("tasks.status_available");
  if (value === "completed") return t("tasks.status_completed");
  if (value === "cooldown") return t("tasks.status_cooldown");
  if (value === "daily_limit") return t("tasks.come_tomorrow");
  if (value === "claimed") return t("tasks.status_claimed");
  if (value === "not_started") return t("tasks.status_not_started");
  if (value === "pending_check") return t("tasks.status_pending_check");
  if (value === "approved") return t("tasks.status_approved");
  if (value === "auto_paid") return t("tasks.status_auto_paid");
  if (value === "rejected") return t("tasks.status_rejected");
  return t("tasks.status_unknown");
}

export function taskStatusVisualState(
  status: string | null | undefined,
): "done" | "wait" | "ready" {
  const value = norm(status);
  const doneStates = [
    "claimed",
    "completed",
    "approved",
    "auto_paid",
  ];
  if (doneStates.includes(value)) return "done";
  if (["cooldown", "pending_check", "daily_limit"].includes(value)) return "wait";
  return "ready";
}

export function balanceHistoryReasonLabel(
  reason: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(reason);
  if (!value) return t("history.reason.unknown");
  if (value.startsWith("task_bonus")) {
    return t("history.reason.task_bonus");
  }
  if (value.startsWith("ad_bonus")) return t("history.reason.ad_bonus");
  if (value.includes("exchange")) {
    return t("history.reason.exchange_kwh");
  }
  if (value.includes("panel")) {
    return t("history.reason.panel_purchase");
  }
  if (value.includes("referral")) {
    return t("history.reason.referral_bonus");
  }
  if (value.includes("withdraw")) return t("history.reason.withdraw");
  if (value.includes("deposit")) return t("history.reason.deposit");
  if (value.includes("payment")) return t("history.reason.payment");
  if (value.includes("order") || value.includes("shop")) {
    return t("history.reason.shop_purchase");
  }
  if (value === "admin_credit" || (value.includes("admin_manual") && value.includes("credit"))) {
    return t("history.reason.admin_credit");
  }
  if (value === "admin_debit" || (value.includes("admin_manual") && value.includes("debit"))) {
    return t("history.reason.admin_debit");
  }
  return t("history.reason.unknown");
}



export function historySourceLabel(
  source: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(source);
  if (value === "ledger") return t("history.detail_balance");
  if (value === "withdraw_request") return t("withdraw.request_short");
  return t("history.reason.unknown");
}

export function historyOperationKindLabel(
  kind: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(kind);
  if (value === "balance_transfer") return t("history.detail_balance");
  if (value === "exchange") return t("history.filter_exchange");
  if (value === "withdraw_request") return t("withdraw.request_short");
  return t("history.reason.unknown");
}

export function historyStatusLabel(
  status: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(status);
  if (value === "completed" || value === "done" || value === "success") {
    return t("history.status_completed");
  }
  if (value === "pending" || value === "queued" || value === "under_review") {
    return t("history.status_pending");
  }
  if (value === "approved") return t("history.status_approved");
  if (value === "paid") return t("history.status_paid");
  if (value === "rejected") return t("history.status_rejected");
  if (value === "canceled" || value === "cancelled") {
    return t("history.status_canceled");
  }
  if (value === "failed" || value === "error") return t("history.status_failed");
  if (value === "processing" || value === "network_processing" || value === "retrying") {
    return t("history.status_processing");
  }
  if (value === "confirming" || value === "external_detected") {
    return t("history.status_confirming");
  }
  return t("history.status_unknown");
}

export function withdrawStatusLabel(
  status: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(status);
  if (value === "pending" || value === "approved" || value === "processing") {
    return t("withdraw.status_pending");
  }
  if (value === "paid") return t("withdraw.status_paid");
  if (value === "canceled" || value === "cancelled") {
    return t("withdraw.status_canceled");
  }
  if (value === "rejected" || value === "failed" || value === "error") {
    return t("withdraw.status_rejected");
  }
  return t("withdraw.status_unknown");
}

export function withdrawOutcomeKindLabel(
  kind: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(kind);
  if (value === "success") return t("withdraw.outcome_success");
  if (value === "reject" || value === "rejected") {
    return t("withdraw.outcome_rejected");
  }
  if (value === "failed" || value === "error") {
    return t("withdraw.outcome_failed");
  }
  if (value === "pending" || value === "manual_review") {
    return t("withdraw.outcome_pending");
  }
  if (value === "canceled" || value === "cancelled") {
    return t("withdraw.outcome_canceled");
  }
  return t("withdraw.outcome_unknown");
}

export function balanceTypeLabel(
  balanceType: string | null | undefined,
  t: TranslationFn,
): string {
  const value = norm(balanceType);
  if (value === "main") return t("withdraw.balance_main");
  if (value === "bonus") return t("withdraw.balance_bonus");
  return t("withdraw.balance_unknown");
}

export function adminWithdrawStatusLabel(
  status: string | null | undefined,
): string {
  const value = norm(status);
  const labels: Record<string, string> = {
    pending: "Ожидает обработки",
    approved: "Одобрено",
    rejected: "Отклонено",
    canceled: "Отменено",
    cancelled: "Отменено",
    paid: "Выплачено",
    failed: "Ошибка выплаты",
    error: "Ошибка выплаты",
  };
  return labels[value] || "Статус не определён";
}

export function adminWithdrawOutcomeLabel(
  outcome: string | null | undefined,
): string {
  const value = norm(outcome);
  const labels: Record<string, string> = {
    success: "Успешный результат",
    reject: "Отклонение",
    rejected: "Отклонение",
    failed: "Ошибка результата",
    error: "Ошибка результата",
    pending: "Ожидает обработки",
  };
  return labels[value] || "Результат не определён";
}

export function adminShopStatusLabel(
  status: string | null | undefined,
): string {
  const value = norm(status);
  const labels: Record<string, string> = {
    live: "Опубликовано",
    hidden: "Скрыто",
    draft: "Архив",
    active: "Активна",
    inactive: "Неактивна",
  };
  return labels[value] || "Статус не определён";
}

export function adminShopItemTypeLabel(
  itemType: string | null | undefined,
): string {
  const value = norm(itemType);
  const labels: Record<string, string> = {
    efhc_package: "Пакет EFHC",
    nft_vip: "NFT / VIP",
    external_link: "Внешний товар",
    custom: "Другой товар",
  };
  return labels[value] || "Товар";
}

export function adminShopActionModeLabel(
  actionMode: string | null | undefined,
): string {
  const value = norm(actionMode);
  const labels: Record<string, string> = {
    checkout: "Оплата через магазин",
    external_link: "Переход на внешнюю страницу",
  };
  return labels[value] || "Способ покупки не определён";
}

export function adminShopDeliveryModeLabel(
  deliveryMode: string | null | undefined,
): string {
  const value = norm(deliveryMode);
  const labels: Record<string, string> = {
    bank_credit: "Автоматически зачислить EFHC",
    manual: "Выдать вручную",
    external: "Выдача на внешней площадке",
  };
  return labels[value] || "Способ выдачи не определён";
}

export function adminTaskSubmissionStatusLabel(
  status: string | null | undefined,
): string {
  const value = norm(status);
  const labels: Record<string, string> = {
    pending: "Ожидает проверки",
    approved: "Подтверждено",
    rejected: "Отклонено",
  };
  return labels[value] || "Состояние не определено";
}
