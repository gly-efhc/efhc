import React, { useContext } from "react";
import { useT } from "../../../hooks/useT";
import { LayoutContext } from "../../Layout";
import { BalanceHistoryEmptyState } from "./BalanceHistoryEmptyState";
import { BalanceHistoryLoadMore } from "./BalanceHistoryLoadMore";
import type { DbId } from "../../../types/db-id";

export type ExchangeHistoryModel = {
  id: DbId;
  created_at: string;
  amount_kwh: string;
  amount_efhc: string;
  reason: string;
};

type Props = {
  items: ExchangeHistoryModel[];
  loading: boolean;
  nextCursor: string | null;
  onLoadMore: () => void;
};

function formatDateTime(value: string, locale: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale, {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function ExchangeHistoryList(props: Props) {
  const t = useT();
  const { lang } = useContext(LayoutContext);
  if (props.loading && props.items.length === 0) {
    return <div className="text-xs text-[color:var(--tg-hint)]">{t("history.loading_items")}</div>;
  }
  if (!props.loading && props.items.length === 0) return <BalanceHistoryEmptyState />;
  return (
    <div className="efhc-history-list efhc-history-table" role="table" data-history-table="exchange" data-history-exchange-source="exchange-history">
      <div className="efhc-history-table-head efhc-history-table-head--exchange" role="row">
        <span>{t("withdraw.created_at")}</span>
        <span>kWh</span>
        <span>EFHCm</span>
      </div>
      {props.items.map((item) => (
        <div className="efhc-history-table-row efhc-history-table-row--exchange" role="row" key={item.id}>
          <time className="efhc-history-table-date" dateTime={item.created_at}>{formatDateTime(item.created_at, lang)}</time>
          <strong className="efhc-history-table-number efhc-financial-number">{item.amount_kwh}</strong>
          <strong className="efhc-history-table-number efhc-financial-number">{item.amount_efhc}</strong>
          <div className="efhc-history-table-reason" title={item.reason}>#{item.id} · {item.reason}</div>
        </div>
      ))}
      {props.nextCursor ? <BalanceHistoryLoadMore onLoadMore={props.onLoadMore} /> : null}
    </div>
  );
}
