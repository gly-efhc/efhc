export const FAQ_SEARCH_RESULT_LIMIT = 24;

export const FAQ_SEARCH_FIELD_WEIGHTS = {
  answer: 1,
  keywords: 4,
  question: 5,
  section: 2,
  subsection: 3,
} as const;

type SearchableFaqText = {
  answer: string;
  keywords: string;
  question: string;
  section: string;
  subsection: string;
};

export function faqSearchNorm(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ё/g, "е")
    .replace(/[^\p{L}\p{N}\s]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function faqSearchTerms(value: string): string[] {
  return faqSearchNorm(value).split(" ").filter(Boolean);
}

export function scoreFaqSearchText(
  text: SearchableFaqText,
  terms: string[],
): number {
  let score = 0;
  for (const term of terms) {
    if (text.question.includes(term)) {
      score += FAQ_SEARCH_FIELD_WEIGHTS.question;
    }
    if (text.keywords.includes(term)) {
      score += FAQ_SEARCH_FIELD_WEIGHTS.keywords;
    }
    if (text.subsection.includes(term)) {
      score += FAQ_SEARCH_FIELD_WEIGHTS.subsection;
    }
    if (text.section.includes(term)) {
      score += FAQ_SEARCH_FIELD_WEIGHTS.section;
    }
    if (text.answer.includes(term)) {
      score += FAQ_SEARCH_FIELD_WEIGHTS.answer;
    }
  }
  return score;
}

export function compareFaqSearchOrder(
  left: { item: { id: string }; score: number },
  right: { item: { id: string }; score: number },
): number {
  if (right.score !== left.score) return right.score - left.score;
  return left.item.id.localeCompare(right.item.id);
}
