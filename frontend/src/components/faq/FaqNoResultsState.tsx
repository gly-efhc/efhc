import React from "react";
import { TelegramEmptyState } from "../ui/telegram/TelegramEmptyState";
import { useT } from "../../hooks/useT";

export function FaqNoResultsState(
  props: { title: string; detail: string; onReset: () => void },
) {
  const t = useT();
  return (
    <TelegramEmptyState
      title={props.title}
      detail={props.detail}
      actionLabel={t("faq.reset_search")}
      onAction={props.onReset}
    />
  );
}
