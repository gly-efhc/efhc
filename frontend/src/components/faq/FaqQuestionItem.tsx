import React from "react";
import type { FaqItem } from "../../data/faq/types";
import {
  TelegramAccordionItem,
} from "../ui/telegram/TelegramAccordionItem";
import { FaqKeywordTags } from "./FaqKeywordTags";
import { FaqAnswerText } from "./FaqAnswerText";
import { getFaqAccordionIds } from "./faqAccordionIds";

type Props = {
  item: FaqItem;
  isOpen: boolean;
  onToggle: () => void;
};

export function FaqQuestionItem(props: Props) {
  const ids = getFaqAccordionIds(props.item.id);
  return (
    <TelegramAccordionItem
      title={props.item.question}
      isOpen={props.isOpen}
      triggerId={ids.triggerId}
      panelId={ids.panelId}
      onToggle={props.onToggle}
      answer={<FaqAnswerText text={props.item.answer} />}
      tags={<FaqKeywordTags tags={props.item.keywords} />}
    />
  );
}
