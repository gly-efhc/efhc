import React from "react";

type Tone =
  | "active"
  | "inactive"
  | "primary"
  | "vip"
  | "main"
  | "bonus"
  | "connected"
  | "warning"
  | "neutral";

const byTone: Record<Tone, string> = {
  active: "bg-[var(--tg-button)] text-[var(--tg-button-text)]",
  inactive: "bg-[var(--tg-secondary-bg)] text-[var(--tg-hint)]",
  primary: "bg-[var(--tg-button)] text-[var(--tg-button-text)]",
  vip: "bg-amber-400/20 text-amber-300",
  main: "bg-emerald-400/20 text-emerald-300",
  bonus: "bg-sky-400/20 text-sky-300",
  connected: "bg-emerald-400/20 text-emerald-300",
  warning: "bg-amber-400/20 text-amber-300",
  neutral: "bg-[var(--tg-secondary-bg)] text-[var(--tg-text)]",
};

export function TelegramStatusBadge(
  props: {
    label: string;
    tone?: Tone;
    icon?: React.ReactNode;
    dataStatus?: string;
  },
) {
  return (
    <span
      data-status={props.dataStatus}
      className={[
        "inline-flex items-center rounded-full px-2.5 py-1",
        "text-[11px] font-semibold",
        byTone[props.tone || "neutral"],
      ].join(" ")}
    >
      {props.icon ? (
        <span aria-hidden="true" className="efhc-status-badge_icon">
          {props.icon}
        </span>
      ) : null}
      <span>{props.label}</span>
    </span>
  );
}
