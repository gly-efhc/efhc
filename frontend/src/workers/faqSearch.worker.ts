import {
  compareFaqSearchOrder,
  FAQ_SEARCH_RESULT_LIMIT,
  faqSearchNorm,
  faqSearchTerms,
  scoreFaqSearchText,
} from "../data/faq/searchContract";
import type {
  FaqCatalog,
  FaqItem,
  FaqSection,
  FaqSubsection,
} from "../data/faq/types";

type IndexedFaq = {
  answer: string;
  item: FaqItem;
  keywords: string;
  question: string;
  section: FaqSection;
  sectionText: string;
  subsection: FaqSubsection;
  subsectionText: string;
};

type InitMessage = {
  catalog: FaqCatalog;
  type: "INIT";
};

type SearchMessage = {
  id: number;
  query: string;
  type: "SEARCH";
};

let index: IndexedFaq[] = [];

function buildIndex(catalog: FaqCatalog): IndexedFaq[] {
  const next: IndexedFaq[] = [];
  for (const section of catalog.sections) {
    for (const subsection of section.subsections) {
      for (const item of subsection.items) {
        next.push({
          answer: faqSearchNorm(item.answer),
          item,
          keywords: faqSearchNorm((item.keywords || []).join(" ")),
          question: faqSearchNorm(item.question),
          section,
          sectionText: faqSearchNorm(section.title),
          subsection,
          subsectionText: faqSearchNorm(subsection.title),
        });
      }
    }
  }
  return next;
}

function search(query: string) {
  const queryTerms = faqSearchTerms(query);
  if (!queryTerms.length) return [];
  return index
    .map((entry) => {
      const score = scoreFaqSearchText(
        {
          answer: entry.answer,
          keywords: entry.keywords,
          question: entry.question,
          section: entry.sectionText,
          subsection: entry.subsectionText,
        },
        queryTerms,
      );
      return {
        item: entry.item,
        score,
        section: entry.section,
        subsection: entry.subsection,
      };
    })
    .filter((entry) => entry.score > 0)
    .sort(compareFaqSearchOrder)
    .slice(0, FAQ_SEARCH_RESULT_LIMIT);
}

self.addEventListener("message", (event: MessageEvent) => {
  const message = event.data as InitMessage | SearchMessage;
  if (message.type === "INIT") {
    index = buildIndex(message.catalog);
    self.postMessage({ size: index.length, type: "READY" });
    return;
  }
  if (message.type === "SEARCH") {
    self.postMessage({
      id: message.id,
      results: search(message.query),
      type: "RESULTS",
    });
  }
});
