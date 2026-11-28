import {
  compareFaqSearchOrder,
  faqSearchNorm,
  faqSearchTerms,
  scoreFaqSearchText,
} from "./searchContract";
import type {
  FaqCatalog,
  FaqItem,
  FaqSearchHit,
  FaqSection,
  FaqSubsection,
} from "./types";

export function faqCounts(catalog: FaqCatalog): {
  sections: number;
  subsections: number;
  items: number;
} {
  const sections = catalog.sections.length;
  const subsections = catalog.sections.reduce(
    (sum, section) => sum + section.subsections.length,
    0,
  );
  const items = catalog.sections.reduce(
    (sum, section) => {
      return sum + section.subsections.reduce(
        (inner, subsection) => inner + subsection.items.length,
        0,
      );
    },
    0,
  );
  return { sections, subsections, items };
}

export function findSection(
  catalog: FaqCatalog,
  sectionId: string | null,
): FaqSection | null {
  if (!sectionId) return null;
  return catalog.sections.find((section) => section.id === sectionId)
    || null;
}

export function findSubsection(
  catalog: FaqCatalog,
  sectionId: string | null,
  subsectionId: string | null,
): FaqSubsection | null {
  const section = findSection(catalog, sectionId);
  if (!section || !subsectionId) return null;
  return section.subsections.find(
    (subsection) => subsection.id === subsectionId,
  ) || null;
}

export function findFaqItem(
  catalog: FaqCatalog,
  itemId: string | null,
): {
  item: FaqItem;
  section: FaqSection;
  subsection: FaqSubsection;
} | null {
  if (!itemId) return null;
  for (const section of catalog.sections) {
    for (const subsection of section.subsections) {
      const item = subsection.items.find(
        (entry) => entry.id === itemId,
      );
      if (item) {
        return { item, section, subsection };
      }
    }
  }
  return null;
}

export function getFaqPreviewItems(
  catalog: FaqCatalog,
  picks: Array<{ sectionId: string; subsectionId: string }>,
  limit = 4,
): Array<{
  item: FaqItem;
  section: FaqSection;
  subsection: FaqSubsection;
}> {
  const result: Array<{
    item: FaqItem;
    section: FaqSection;
    subsection: FaqSubsection;
  }> = [];

  for (const pick of picks) {
    const section = findSection(catalog, pick.sectionId);
    const subsection = findSubsection(
      catalog,
      pick.sectionId,
      pick.subsectionId,
    );
    if (!section || !subsection) continue;
    for (const item of subsection.items) {
      result.push({ item, section, subsection });
      if (result.length >= limit) return result;
    }
  }

  return result.slice(0, limit);
}

export function getRelatedFaqItems(
  catalog: FaqCatalog,
  activeItemId: string | null,
  sectionId: string | null,
  subsectionId: string | null,
  limit = 6,
): FaqItem[] {
  const current = findFaqItem(catalog, activeItemId);
  if (current?.item.relatedIds?.length) {
    const related = current.item.relatedIds
      .map((id) => findFaqItem(catalog, id)?.item || null)
      .filter((item): item is FaqItem => Boolean(item));
    if (related.length) return related.slice(0, limit);
  }

  const subsection = findSubsection(catalog, sectionId, subsectionId);
  if (!subsection) return [];
  return subsection.items.filter((item) => item.id !== activeItemId)
    .slice(0, limit);
}

export function searchFaq(
  catalog: FaqCatalog,
  query: string,
): FaqSearchHit[] {
  const terms = faqSearchTerms(query);
  if (!terms.length) return [];
  const hits: FaqSearchHit[] = [];

  for (const section of catalog.sections) {
    const sectionText = faqSearchNorm(section.title);
    for (const subsection of section.subsections) {
      const subsectionText = faqSearchNorm(subsection.title);
      for (const item of subsection.items) {
        const score = scoreFaqSearchText(
          {
            answer: faqSearchNorm(item.answer),
            keywords: faqSearchNorm((item.keywords || []).join(" ")),
            question: faqSearchNorm(item.question),
            section: sectionText,
            subsection: subsectionText,
          },
          terms,
        );

        if (score > 0) {
          hits.push({
            item,
            section,
            subsection,
            score,
          });
        }
      }
    }
  }

  return hits.sort(compareFaqSearchOrder);
}
