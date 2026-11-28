import React, { useContext } from "react";
import type { DbId } from "../../../types/db-id";
import { LayoutContext } from "../../Layout";

export type BalanceHistoryModel = {
  id: DbId;
  amount_efhc: string;
  direction: "credit" | "debit";
  balance_type: "main" | "bonus";
  reason: string;
  created_at: string;
};

type Props = {
  item: BalanceHistoryModel;
  reasonLabel: (reason: string) => string;
  showDateTime?: boolean;
};

function amountPrefix(direction: "credit" | "debit"): string {
  return direction === "credit" ? "+" : "−";
}

function dateTimeLabel(value: string, locale: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function BalanceHistoryItem(props: Props) {
  const { lang } = useContext(LayoutContext);
  const { item } = props;
  const asset = item.balance_type === "bonus" ? "EFHCb" : "EFHCm";
  const reason = props.reasonLabel(item.reason);
  return (
    <div
      className="efhc-operation-row"
      data-operation-direction={item.direction}
      data-operation-id={item.id}
      role="listitem"
    >
      <span className="efhc-operation-sign" aria-hidden="true">
        {amountPrefix(item.direction)}
      </span>
      <span className="efhc-operation-name" title={`${reason} · ${asset}`}>
        <span>{reason} · {asset}</span>
        {props.showDateTime ? (
          <time className="efhc-operation-inline-date" dateTime={item.created_at}>
            {dateTimeLabel(item.created_at, lang)}
          </time>
        ) : null}
      </span>
      <strong className="efhc-operation-amount efhc-financial-number">
        {item.amount_efhc}
      </strong>
    </div>
  );
}
