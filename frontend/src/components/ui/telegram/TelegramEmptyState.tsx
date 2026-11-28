import React from "react";
import { Button } from "../Button";

type Props = {
  title: string;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function TelegramEmptyState(props: Props) {
  return (
    <div
      className={[
        "efhc-user-empty-block rounded-3xl border px-4 py-5 text-center",
        "border-[color:var(--tg-hint)]/20",
        "bg-[var(--tg-secondary-bg)]/80",
      ].join(" ")}
    >
      <div className="text-lg">◌</div>
      <div className="mt-2 text-sm font-semibold">{props.title}</div>
      {props.detail ? (
        <div className="mt-1 text-sm text-[color:var(--tg-hint)]">
          {props.detail}
        </div>
      ) : null}
      {props.actionLabel && props.onAction ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" onClick={props.onAction}>
            {props.actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
