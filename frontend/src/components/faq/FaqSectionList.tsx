import React from "react";
import type { FaqSection } from "../../data/faq/types";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";

type Props = {
  sections: FaqSection[];
  countLabel: string;
  questionsLabel: string;
  onOpen: (sectionId: string) => void;
};

export function FaqSectionList(props: Props) {
  return (
    <div className="grid gap-3">
      {props.sections.map((section) => {
        const itemCount = section.subsections.reduce(
          (sum, subsection) => sum + subsection.items.length,
          0,
        );
        const redundantSingleSubsection = section.subsections.length === 1
          && section.subsections[0].title.trim().toLocaleLowerCase()
            === section.title.trim().toLocaleLowerCase();
        return (
          <TelegramSectionRow
            key={section.id}
            title={`${section.id}. ${section.title}`}
            subtitle={redundantSingleSubsection
              ? `${itemCount} ${props.questionsLabel}`
              : [
                `${section.subsections.length} ${props.countLabel}`,
                `${itemCount} ${props.questionsLabel}`,
              ].join(" / ")}
            onClick={() => props.onOpen(section.id)}
          />
        );
      })}
    </div>
  );
}
