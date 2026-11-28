export type FaqAccordionIds = Readonly<{
  triggerId: string;
  panelId: string;
}>;

export function getFaqAccordionIds(itemId: string): FaqAccordionIds {
  const token = encodeURIComponent(itemId.trim());
  if (!token) {
    throw new Error("FAQ accordion item id must be provided");
  }
  return {
    triggerId: `faq-accordion-trigger-${token}`,
    panelId: `faq-accordion-panel-${token}`,
  };
}
