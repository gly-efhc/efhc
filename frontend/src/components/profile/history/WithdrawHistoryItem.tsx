import React, { useContext } from "react";
import { useT } from "../../../hooks/useT";
import { LayoutContext } from "../../Layout";
import type { DbId } from "../../../types/db-id";

export type WithdrawHistoryModel = {
  id: DbId;
  global_id: string;
  amount: string;
  status: string;
  created_at: string;
  updated_at: string;
};

type Props = { item: WithdrawHistoryModel };

function formatDateTime(value: string, locale: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale, {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function WithdrawHistoryItem(props: Props) {
  const t = useT();
  const { lang } = useContext(LayoutContext);
  const { item } = props;
  const statusMap: Record<string, string> = {
    PENDING: t("withdraw.status_pending"),
    APPROVED: t("withdraw.status_approved"),
    PAID: t("withdraw.status_paid"),
    REJECTED: t("withdraw.status_rejected"),
    CANCELED: t("withdraw.status_canceled"),
  };
  return (
    <div className="efhc-withdraw-history-row" data-status={item.status}>
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-xs">
          <strong>#{item.id}</strong>
          <span>{statusMap[item.status] || item.status}</span>
        </div>
        <time className="text-[11px] text-[color:var(--tg-hint)]" dateTime={item.created_at}>
          {formatDateTime(item.created_at, lang)}
        </time>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-[11px] text-[color:var(--tg-hint)]">EFHCm</div>
        <strong className="efhc-financial-number">{item.amount}</strong>
      </div>
    </div>
  );
}
