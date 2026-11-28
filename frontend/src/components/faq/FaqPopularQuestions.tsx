import React from "react";
import type {
  FaqItem,
  FaqSection,
  FaqSubsection,
} from "../../data/faq/types";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";

type Entry = {
  item: FaqItem;
  section: FaqSection;
  subsection: FaqSubsection;
};

export function FaqPopularQuestions(
  props: { items: Entry[]; onOpen: (e: Entry) => void },
) {
  if (!props.items.length) return null;
  return (
    <div className="grid gap-2">
      {props.items.map((entry) => (
        <TelegramSectionRow
          key={entry.item.id}
          title={entry.item.question}
          subtitle={
            `${entry.section.title} · ${entry.subsection.title}`
          }
          onClick={() => props.onOpen(entry)}
          compact
        />
      ))}
    </div>
  );
}
