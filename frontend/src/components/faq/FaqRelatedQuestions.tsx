import React from "react";
import type { FaqItem } from "../../data/faq/types";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";

type Props = {
  title: string;
  items: FaqItem[];
  onOpen: (itemId: string) => void;
};

export function FaqRelatedQuestions(props: Props) {
  if (!props.items.length) return null;
  return (
    <div className="grid gap-2">
      <div className="text-sm font-semibold">{props.title}</div>
      {props.items.map((item) => (
        <TelegramSectionRow
          key={item.id}
          title={item.question}
          onClick={() => props.onOpen(item.id)}
          compact
        />
      ))}
    </div>
  );
}
