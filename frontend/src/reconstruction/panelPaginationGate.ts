/** EFHC portfolio: one 20-row page per new bottom-scroll intention. */
export type PanelPaginationTrigger = {
  tab: "active" | "archive";
  direction: "oldest" | "newest";
  itemCount: number;
  scrollTop: number;
};

export function shouldRequestNextPanelPage(input: {
  tab: "active" | "archive";
  direction: "oldest" | "newest";
  itemCount: number;
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
  lastTrigger: PanelPaginationTrigger | null;
  inFlight: boolean;
  loading: boolean;
  canLoadMore: boolean;
}): boolean {
  if (input.inFlight || input.loading || !input.canLoadMore) return false;
  if (input.clientHeight <= 0 || input.scrollHeight <= input.clientHeight) return false;
  if (input.scrollHeight - input.scrollTop - input.clientHeight > 180) return false;
  const previous = input.lastTrigger;
  if (
    previous &&
    previous.tab === input.tab &&
    previous.direction === input.direction &&
    // Advance by half a viewport after a page request. React updates,
    // scroll anchoring and duplicate scroll events do not constitute a new
    // user intention to fetch the next 20 records.
    input.scrollTop < previous.scrollTop + Math.max(64, input.clientHeight / 2)
  ) return false;
  return true;
}
