import type { QueryClient } from "@tanstack/react-query";

/** Reads are activity-driven and coalesced. This never replays a mutation. */
export function startActivitySync(client: QueryClient, target: EventTarget = window): () => void {
  let last = 0, running = false;
  const events = ["pointerdown", "pointermove", "touchstart", "keydown", "scroll", "focus", "visibilitychange"];
  const sync = () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    const now = Date.now();
    if (running || now - last < 10_000) return;
    last = now; running = true;
    target.dispatchEvent(new Event("efhc:activity-sync"));
    void client.refetchQueries({type: "active", predicate: query => query.state.fetchStatus === "idle" && query.isStale()})
      .finally(() => {running = false;});
  };
  for (const event of events) target.addEventListener(event, sync, {passive: true, capture: true});
  return () => {for (const event of events) target.removeEventListener(event, sync, {capture: true});};
}
