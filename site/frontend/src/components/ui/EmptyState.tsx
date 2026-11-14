import React from "react";
import { Button } from "./Button";

export function EmptyState(
  props: {
    title: string;
    detail?: string;
    actionLabel?: string;
    onAction?: () => void;
    intent?: "error" | "neutral";
  },
) {
  const containerCls = [
    "border border-[color:var(--tg-hint)]",
    "rounded-2xl",
    "p-4",
    "bg-[color:var(--tg-secondary-bg)]/40",
  ].join(" ");
  return (
    <div
      className={containerCls}
      data-user-feedback-kind={props.intent}
      role={props.intent === "error" ? "alert" : undefined}
    >
      <div className="font-semibold">{props.title}</div>
      {props.detail ? (
        <div className="text-sm text-[color:var(--tg-hint)] mt-1">
          {props.detail}
        </div>
      ) : null}
      {props.actionLabel && props.onAction ? (
        <div className="mt-3">
          <Button variant="secondary" onClick={props.onAction}>
            {props.actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
