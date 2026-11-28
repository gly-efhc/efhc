import React from "react";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "../ui/telegram/TelegramStatusBadge";

type LinkItem = {
  id: string;
  label: string;
  subtitle?: string;
  badge?: string;
  tone?: "primary" | "neutral" | "connected" | "warning" | "vip";
  onClick: () => void;
};

export function FaqQuickLinks(props: {
  items: LinkItem[];
  title?: string;
  description?: string;
}) {
  if (!props.items.length) return null;
  return (
    <div className="space-y-3">
      {props.title ? (
        <div>
          <div className="text-sm font-semibold">{props.title}</div>
          {props.description ? (
            <div className="mt-1 text-xs text-[color:var(--tg-hint)]">
              {props.description}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="grid gap-2">
        {props.items.map((item) => (
          <TelegramSectionRow
            key={item.id}
            compact
            title={item.label}
            subtitle={item.subtitle}
            onClick={item.onClick}
            rightSlot={
              item.badge ? (
                <TelegramStatusBadge
                  label={item.badge}
                  tone={item.tone || "neutral"}
                />
              ) : null
            }
          />
        ))}
      </div>
    </div>
  );
}
