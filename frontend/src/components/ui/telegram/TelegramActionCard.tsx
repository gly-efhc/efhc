import React from "react";
import { Button } from "../Button";

type Props = {
  title: string;
  description: string;
  primaryLabel: string;
  onPrimary: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
  emphasis?: boolean;
  disabled?: boolean;
};

export function TelegramActionCard(props: Props) {
  return (
    <div
      className={[
        "rounded-3xl border p-4",
        props.emphasis
          ? "efhc-energy-hero"
          : "bg-[var(--tg-secondary-bg)]",
      ].join(" ")}
    >
      <div className="text-sm font-semibold">{props.title}</div>
      <div className="mt-1 text-sm text-[color:var(--tg-hint)]">
        {props.description}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          onClick={props.onPrimary}
          disabled={props.disabled}
        >
          {props.primaryLabel}
        </Button>
        {props.secondaryLabel && props.onSecondary ? (
          <Button variant="secondary" onClick={props.onSecondary}>
            {props.secondaryLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
