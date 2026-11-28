export type FaqRouteState = {
  sectionId: string | null;
  subsectionId: string | null;
  itemId: string | null;
};

export function faqQuery(state: FaqRouteState): Record<string, string> {
  const query: Record<string, string> = {};
  if (state.sectionId) query.section = state.sectionId;
  if (state.subsectionId) query.subsection = state.subsectionId;
  if (state.itemId) query.item = state.itemId;
  return query;
}
