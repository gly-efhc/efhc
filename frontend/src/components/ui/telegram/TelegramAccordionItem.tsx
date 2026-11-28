import React from "react";

type Props = {
  title: string;
  answer?: React.ReactNode;
  isOpen: boolean;
  triggerId: string;
  panelId: string;
  onToggle: () => void;
  tags?: React.ReactNode;
  related?: React.ReactNode;
};

export function TelegramAccordionItem(props: Props) {
  return (
    <div
      className={[
        "rounded-2xl border px-4 py-3",
        "border-[color:var(--tg-hint)]/20",
        "bg-[var(--tg-secondary-bg)]",
      ].join(" ")}
    >
      <button
        id={props.triggerId}
        type="button"
        aria-expanded={props.isOpen}
        aria-controls={props.panelId}
        onClick={props.onToggle}
        className="flex w-full items-start gap-3 text-left"
      >
        <div className="flex-1 text-sm font-semibold">
          {props.title}
        </div>
        <div className="pt-0.5 text-lg leading-none">
          {props.isOpen ? "−" : "+"}
        </div>
      </button>
      {props.isOpen ? (
        <div id={props.panelId} className="mt-3 space-y-3 overflow-hidden">
          {props.answer ? (
            <div className="text-sm leading-6">{props.answer}</div>
          ) : null}
          {props.tags}
          {props.related}
        </div>
      ) : null}
    </div>
  );
}
