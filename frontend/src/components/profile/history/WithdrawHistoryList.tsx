import React from "react";
import { useT } from "../../../hooks/useT";
import { BalanceHistoryEmptyState } from "./BalanceHistoryEmptyState";
import {
  WithdrawHistoryItem,
  type WithdrawHistoryModel,
} from "./WithdrawHistoryItem";
import { BalanceHistoryLoadMore } from "./BalanceHistoryLoadMore";

type Props = {
  items: WithdrawHistoryModel[];
  loading: boolean;
  nextCursor: string | null;
  onLoadMore: () => void;
};

export function WithdrawHistoryList(props: Props) {
  const t = useT();
  if (props.loading && props.items.length === 0) {
    return <div className="text-xs text-[color:var(--tg-hint)]">{t("withdraw.loading_items")}</div>;
  }
  if (!props.loading && props.items.length === 0) {
    return <BalanceHistoryEmptyState title={t("withdraw.empty_title")} body={t("withdraw.empty_body")} />;
  }
  return (
    <div className="efhc-withdraw-history-list space-y-1.5" data-history-withdraw-list="true">
      {props.items.map((item) => <WithdrawHistoryItem key={item.id} item={item} />)}
      {props.nextCursor ? <BalanceHistoryLoadMore onLoadMore={props.onLoadMore} /> : null}
    </div>
  );
}
