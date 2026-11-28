import type { Lang } from "../../lib/i18n";

type FaqItemOverride = {
  question?: string;
  answer?: string;
  keywords?: string[];
};

type FaqOverridesByLang = Partial<
  Record<Lang, Record<string, FaqItemOverride>>
>;

export const faqItemOverridesByLang: FaqOverridesByLang = {};
