export type FaqItem = {
  id: string;
  question: string;
  answer: string;
  keywords?: string[];
  relatedIds?: string[];
};

export type FaqSubsection = {
  id: string;
  title: string;
  items: FaqItem[];
};

export type FaqSection = {
  id: string;
  title: string;
  subsections: FaqSubsection[];
};

export type FaqCatalog = {
  title: string;
  sections: FaqSection[];
};

export type FaqSearchHit = {
  item: FaqItem;
  section: FaqSection;
  subsection: FaqSubsection;
  score: number;
};
