import React from "react";
import type { FaqSection } from "../../data/faq/types";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";

type Props = {
  section: FaqSection;
  questionsLabel: string;
  onOpen: (sectionId: string, subsectionId: string) => void;
};

export function FaqSubsectionList(props: Props) {
  return (
    <div className="grid gap-3">
      {props.section.subsections.map((subsection) => (
        <TelegramSectionRow
          key={subsection.id}
          title={`${subsection.id} · ${subsection.title}`}
          subtitle={
            `${subsection.items.length} ${props.questionsLabel}`
          }
          onClick={() => props.onOpen(props.section.id, subsection.id)}
        />
      ))}
    </div>
  );
}
