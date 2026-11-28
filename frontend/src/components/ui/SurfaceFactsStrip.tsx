import React from "react";

import { TelegramInfoBlock } from "./telegram/TelegramInfoBlock";
import { TelegramStatusBadge } from "./telegram/TelegramStatusBadge";

type FactItem = {
  label: string;
  tone?: "neutral" | "connected" | "warning" | "primary" | "vip";
};

type Props = {
  title: string;
  description?: string;
  items: FactItem[];
};

export function SurfaceFactsStrip({
  title,
  description,
  items,
}: Props) {
  return (
    <TelegramInfoBlock title={title} description={description}>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.map((item) => (
          <TelegramStatusBadge
            key={item.label}
            label={item.label}
            tone={item.tone || "neutral"}
          />
        ))}
      </div>
    </TelegramInfoBlock>
  );
}
