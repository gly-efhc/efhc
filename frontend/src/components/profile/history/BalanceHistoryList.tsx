import React, { useContext, useMemo } from "react";
import { useT } from "../../../hooks/useT";
import { LayoutContext } from "../../Layout";
import { BalanceHistoryEmptyState } from "./BalanceHistoryEmptyState";
import {
  BalanceHistoryItem,
  type BalanceHistoryModel,
} from "./BalanceHistoryItem";
import { BalanceHistoryLoadMore } from "./BalanceHistoryLoadMore";

type Props = {
  items: BalanceHistoryModel[];
  loading: boolean;
  nextCursor: string | null;
  onLoadMore: () => void;
  reasonLabel: (reason: string) => string;
  layout?: "grouped" | "flat";
};

type DateGroup = {
  key: string;
  label: string;
  items: BalanceHistoryModel[];
};

function dateKey(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateLabel(value: string, locale: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function BalanceHistoryList(props: Props) {
  const t = useT();
  const { lang } = useContext(LayoutContext);
  const groups = useMemo<DateGroup[]>(() => {
    const ordered: DateGroup[] = [];
    const index = new Map<string, DateGroup>();
    for (const item of props.items) {
      const key = dateKey(item.created_at);
      let group = index.get(key);
      if (!group) {
        group = { key, label: dateLabel(item.created_at, lang), items: [] };
        index.set(key, group);
        ordered.push(group);
      }
      group.items.push(item);
    }
    return ordered;
  }, [lang, props.items]);

  if (props.loading && props.items.length === 0) {
    return <div className="text-xs text-[color:var(--tg-hint)]">{t("history.loading_items")}</div>;
  }
  if (!props.loading && props.items.length === 0) return <BalanceHistoryEmptyState />;
  if (props.layout === "flat") {
    return (
      <div className="efhc-operation-history efhc-operation-history--flat" data-history-layout="flat-compact-ledger">
        <div className="efhc-operation-day-list" role="list">
          {props.items.map((item) => (
            <BalanceHistoryItem key={item.id} item={item} reasonLabel={props.reasonLabel} showDateTime />
          ))}
        </div>
        {props.nextCursor ? <BalanceHistoryLoadMore onLoadMore={props.onLoadMore} /> : null}
      </div>
    );
  }
  return (
    <div className="efhc-operation-history" data-history-layout="date-grouped-compact-ledger">
      {groups.map((group) => (
        <section className="efhc-operation-day" key={group.key} data-operation-date={group.key}>
          <div className="efhc-operation-date">{group.label}</div>
          <div className="efhc-operation-day-list" role="list">
            {group.items.map((item) => (
              <div className="efhc-native-virtual-item" key={item.id}>
                <BalanceHistoryItem item={item} reasonLabel={props.reasonLabel} />
              </div>
            ))}
          </div>
        </section>
      ))}
      {props.nextCursor ? <BalanceHistoryLoadMore onLoadMore={props.onLoadMore} /> : null}
    </div>
  );
}
