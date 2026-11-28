import React from "react";
import type { FaqItem, FaqSubsection } from "../../data/faq/types";
import { FaqQuestionItem } from "./FaqQuestionItem";
import { FaqRelatedQuestions } from "./FaqRelatedQuestions";
import { FaqQuickLinks } from "./FaqQuickLinks";
import { useT } from "../../hooks/useT";

type Props = {
  subsection: FaqSubsection;
  openItemIds: ReadonlySet<string>;
  relatedTitle: string;
  relatedItems: FaqItem[];
  onOpen: (itemId: string) => void;
  onQuickWallet: () => void;
  onQuickHistory: () => void;
  onQuickPage: (href: string) => void;
};

export function FaqAccordionList(props: Props) {
  const t = useT();
  return (
    <div className="grid gap-3">
      {props.subsection.items.map((item) => (
        <FaqQuestionItem
          key={item.id}
          item={item}
          isOpen={props.openItemIds.has(item.id)}
          onToggle={() => props.onOpen(item.id)}
        />
      ))}
      <FaqRelatedQuestions
        title={props.relatedTitle}
        items={props.relatedItems}
        onOpen={props.onOpen}
      />
      <FaqQuickLinks
        title={t("faq.quick_topic_links")}
        description={t("faq.quick_topic_links_desc")}
        items={[
          {
            id: "wallet",
            label: "Wallet",
            subtitle: t("faq.quick_wallet_desc"),
            badge: "wallet",
            tone: "connected",
            onClick: props.onQuickWallet,
          },
          {
            id: "history",
            label: t("history.title"),
            subtitle: t("faq.quick_history_desc"),
            badge: "history",
            tone: "neutral",
            onClick: props.onQuickHistory,
          },
          {
            id: "panels",
            label: t("nav.panels"),
            subtitle: t("faq.quick_panels_desc"),
            badge: "panels",
            tone: "primary",
            onClick: () => props.onQuickPage("/panels"),
          },
          {
            id: "exchange",
            label: t("nav.exchange"),
            subtitle: t("faq.quick_exchange_desc"),
            badge: "exchange",
            tone: "primary",
            onClick: () => props.onQuickPage("/exchange"),
          },
          {
            id: "referrals",
            label: t("nav.referrals"),
            subtitle: t("faq.quick_referrals_desc"),
            badge: "referrals",
            tone: "neutral",
            onClick: () => props.onQuickPage("/referrals"),
          },
          {
            id: "ranks",
            label: t("nav.ranks"),
            subtitle: t("faq.quick_ranks_desc"),
            badge: "ranks",
            tone: "neutral",
            onClick: () => props.onQuickPage("/ranks"),
          },
        ]}
      />
    </div>
  );
}
