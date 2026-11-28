import React from "react";

type Props = {
  title: string;
  subtitle?: string;
  leftSlot?: React.ReactNode;
  rightSlot?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  compact?: boolean;
  className?: string;
};

function Content(props: Props) {
  return (
    <div className="flex items-start gap-3">
      {props.leftSlot ? (
        <div className="pt-0.5 shrink-0">{props.leftSlot}</div>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold">{props.title}</div>
        {props.subtitle ? (
          <div className="mt-1 text-xs text-[color:var(--tg-hint)]">
            {props.subtitle}
          </div>
        ) : null}
      </div>
      {props.rightSlot ? (
        <div className="shrink-0">{props.rightSlot}</div>
      ) : null}
    </div>
  );
}

export function TelegramSectionRow(props: Props) {
  const px = props.compact ? "px-3 py-2.5" : "px-4 py-3";
  const cls = [
    "w-full rounded-2xl border text-left transition",
    "border-[color:var(--tg-hint)]/20",
    "bg-[var(--tg-secondary-bg)]",
    "active:scale-[0.99]",
    "disabled:opacity-50 disabled:cursor-not-allowed",
    px,
    props.className || "",
  ].join(" ");
  if (props.onClick) {
    return (
      <button
        type="button"
        onClick={props.onClick}
        disabled={props.disabled}
        className={cls}
      >
        <Content {...props} />
      </button>
    );
  }
  return (
    <div className={cls}>
      <Content {...props} />
    </div>
  );
}
