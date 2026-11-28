import React from "react";
import { useT } from "../../../hooks/useT";
import { TelegramEmptyState } from "../../ui/telegram/TelegramEmptyState";

type Props = {
  title?: string;
  body?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function BalanceHistoryEmptyState(props: Props) {
  const t = useT();
  return (
    <TelegramEmptyState
      title={props.title || t("history.empty_title")}
      detail={props.body || t("history.empty_body")}
      actionLabel={props.actionLabel}
      onAction={props.onAction}
    />
  );
}
