import React, { useContext, useMemo } from "react";
import { useT } from "../../../hooks/useT";
import { LayoutContext } from "../../Layout";
import { BalanceHistoryEmptyState } from "./BalanceHistoryEmptyState";
import { BalanceHistoryLoadMore } from "./BalanceHistoryLoadMore";

export type HistoryOperationTone = "credit" | "debit" | "neutral";

export type HistoryOperationDetail = {
  label: string;
  value: string;
};

export type HistoryOperationModel = {
  key: string;
  title: string;
  subtitle: string;
  createdAt: string;
  executionAt?: string | null;
  amount: string;
  asset: string;
  tone: HistoryOperationTone;
  status: string;
  statusKind: "done" | "pending" | "failed" | "neutral";
  details: HistoryOperationDetail[];
};

type Props = {
  items: HistoryOperationModel[];
  loading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  layout?: "grouped" | "flat";
};

type DateGroup = {
  key: string;
  label: string | null;
  items: HistoryOperationModel[];
};

function displayedTime(item: HistoryOperationModel): string | null {
  return item.executionAt === undefined ? item.createdAt : item.executionAt;
}

function timeSortValue(item: HistoryOperationModel): number {
  const value = displayedTime(item);
  return value ? (parseDate(value)?.getTime() ?? Number.NEGATIVE_INFINITY) : Number.NEGATIVE_INFINITY;
}

function parseDate(value: string): Date | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function dateKey(value: string): string {
  const parsed = parseDate(value);
  if (!parsed) return value;
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateLabel(value: string, locale: string): string {
  const parsed = parseDate(value);
  if (!parsed) return value;
  return parsed.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function dateTimeLabel(value: string, locale: string): string {
  const parsed = parseDate(value);
  if (!parsed) return value;
  return parsed.toLocaleString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function amountPrefix(tone: HistoryOperationTone): string {
  if (tone === "credit") return "+";
  if (tone === "debit") return "−";
  return "";
}

function OperationCard({ item, locale }: { item: HistoryOperationModel; locale: string }) {
  const t = useT();
  const time = displayedTime(item);
  return (
    <details
      className="efhc-history-bank-operation"
      data-operation-tone={item.tone}
      data-status-kind={item.statusKind}
    >
      <summary className="efhc-history-bank-operation-summary">
        <span className="efhc-history-bank-operation-icon" aria-hidden="true">
          {item.tone === "credit" ? "+" : item.tone === "debit" ? "−" : "•"}
        </span>
        <span className="efhc-history-bank-operation-copy">
          <strong>{item.title}</strong>
          {time ? <time dateTime={time}>{dateTimeLabel(time, locale)}</time> : null}
          <span>{item.subtitle}</span>
        </span>
        <span className="efhc-history-bank-operation-value">
          <strong className="efhc-financial-number">
            {amountPrefix(item.tone)}{item.amount}
          </strong>
          <small>{item.asset}</small>
          <em data-status-kind={item.statusKind}>{item.status}</em>
        </span>
      </summary>
      <div className="efhc-history-bank-operation-details">
        <div className="efhc-history-bank-operation-details-title">
          {t("history.details_title")}
        </div>
        {item.details.map((detail, index) => (
          <div className="efhc-history-bank-operation-detail" key={`${item.key}:${index}`}>
            <span>{detail.label}</span>
            <strong>{detail.value}</strong>
          </div>
        ))}
      </div>
    </details>
  );
}

export function HistoryOperationFeed(props: Props) {
  const t = useT();
  const { lang } = useContext(LayoutContext);
  const sorted = useMemo(
    () => [...props.items].sort((a, b) => {
      const aTime = timeSortValue(a);
      const bTime = timeSortValue(b);
      return aTime === bTime ? 0 : bTime - aTime;
    }),
    [props.items],
  );
  const groups = useMemo<DateGroup[]>(() => {
    const ordered: DateGroup[] = [];
    const index = new Map<string, DateGroup>();
    for (const item of sorted) {
      const time = displayedTime(item);
      const key = time ? dateKey(time) : "undated";
      let group = index.get(key);
      if (!group) {
        group = { key, label: time ? dateLabel(time, lang) : null, items: [] };
        index.set(key, group);
        ordered.push(group);
      }
      group.items.push(item);
    }
    return ordered;
  }, [lang, sorted]);

  if (props.loading && sorted.length === 0) {
    return (
      <div className="text-xs text-[color:var(--tg-hint)]" data-history-state="loading">
        {t("history.loading_items")}
      </div>
    );
  }
  if (!props.loading && sorted.length === 0) {
    return (
      <div data-history-state="true-empty">
        <BalanceHistoryEmptyState />
      </div>
    );
  }

  return (
    <div
      className="efhc-history-bank-feed"
      data-history-layout={props.layout === "flat" ? "flat-bank-feed" : "date-grouped-bank-feed"}
    >
      {props.layout === "flat" ? (
        <div className="efhc-history-bank-operation-list" role="list">
          {sorted.map((item) => <OperationCard key={item.key} item={item} locale={lang} />)}
        </div>
      ) : groups.map((group) => (
        <section className="efhc-history-bank-day" key={group.key} data-operation-date={group.label ? group.key : undefined}>
          {group.label ? <div className="efhc-history-bank-day-title">{group.label}</div> : null}
          <div className="efhc-history-bank-operation-list" role="list">
            {group.items.map((item) => <OperationCard key={item.key} item={item} locale={lang} />)}
          </div>
        </section>
      ))}
      {props.hasMore ? <BalanceHistoryLoadMore onLoadMore={props.onLoadMore} /> : null}
    </div>
  );
}
