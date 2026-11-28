import { readShopReview, type ShopReview } from "./shopCheckoutReview";
// Local and deliberately unwired until the ShopOrder persistence and Pay contracts exist.
export type DraftShopState = "not_seen" | "prepared" | "canceled" | "issued" | "paid" | "terminal_unpaid";
export type ShopAction = "prepare" | "status" | "cancel" | "pay";
type ShopReply = { state: DraftShopState; order_id?: string; intent_id?: string; review: ShopReview | null };
type BoundOperation = { key: string; sequence: number; action: ShopAction };
type Session = {
  // Opaque owner-scoped same-request key; do not retain token, raw owner or payment material.
  key: string;
  visible: boolean;
  authoritative: DraftShopState | "unknown";
  operation: BoundOperation | null;
  sequence: number;
  dispatchedFinalAction: "pay" | "cancel" | null;
  refs: Pick<ShopReply, "order_id" | "intent_id">;
  review: ShopReview | null;
};

export function openShopSession(key: string): Session {
  if (!key || key.length > 128) throw new TypeError("Invalid Shop request key");
  return { key, visible: true, authoritative: "unknown", operation: null, sequence: 0, dispatchedFinalAction: null, refs: {}, review: null };
}

// The transport adapter must persist this final-action fence with the opaque key
// before executing a command. Restored sessions start status-only.
export function restoreShopSession(key: string, finalAction: "pay" | "cancel" | null): Session {
  return { ...openShopSession(key), visible: false, sequence: 1, dispatchedFinalAction: finalAction };
}

export function showShopModal(session: Session, visible: boolean): Session {
  // Close/X/Escape/backdrop affect presentation only, not authorization or cancellation.
  return { ...session, visible };
}
export function planShopAction(
  session: Session,
  action: ShopAction,
  options: { explicit: boolean; freshUndispatched?: boolean; wirePayVerified?: boolean },
): { session: Session; command: BoundOperation | null } {
  if (session.operation) return { session, command: null };
  if (action !== "status") {
    if (!options.explicit || !session.visible || session.dispatchedFinalAction) return { session, command: null };
    if (action === "prepare" && (session.authoritative !== "unknown" || !options.freshUndispatched || session.sequence !== 0)) return { session, command: null };
    if ((action === "cancel" || action === "pay") && session.authoritative !== "prepared") return { session, command: null };
    if (action === "pay" && (!options.wirePayVerified || !session.review)) return { session, command: null };
  }
  const command = { key: session.key, sequence: session.sequence + 1, action };
  return { session: { ...session, operation: command, sequence: command.sequence, dispatchedFinalAction: action === "pay" || action === "cancel" ? action : session.dispatchedFinalAction }, command };
}

const states: readonly DraftShopState[] = ["not_seen", "prepared", "canceled", "issued", "paid", "terminal_unpaid"];
function parseReply(raw: unknown): ShopReply | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (!states.includes(data.state as DraftShopState)) return null;
  const id = (value: unknown): value is string => typeof value === "string" &&
    /^[1-9]\d{0,18}$/.test(value) && (value.length < 19 || value <= "9223372036854775807");
  if ((data.order_id !== undefined && !id(data.order_id)) || (data.intent_id !== undefined && !id(data.intent_id))) return null;
  if (["issued", "paid", "terminal_unpaid"].includes(String(data.state)) && !id(data.order_id)) return null;
  if (data.state === "issued" && !id(data.intent_id)) return null;
  const review = data.state === "prepared" ? readShopReview(data.review ?? data) : null;
  if (data.state === "prepared" && !review) return null;
  return { state: data.state as DraftShopState, order_id: data.order_id as string | undefined, intent_id: data.intent_id as string | undefined, review };
}

export function acceptShopReply(session: Session, command: BoundOperation, raw: unknown): Session {
  if (!session.operation || session.key !== command.key || session.operation.sequence !== command.sequence ||
      session.operation.action !== command.action) return session;
  const incoming = parseReply(raw);
  const base = { ...session, operation: null };
  // Known terminal results are immutable in this controller, not editable history.
  if (session.authoritative === "paid" || session.authoritative === "canceled" || session.authoritative === "terminal_unpaid") return base;
  if (!incoming || incoming.state === "not_seen") {
    // A delayed action may still commit; not_seen is not authority to allocate a new key.
    return { ...base, authoritative: session.authoritative === "issued" ? "issued" : "unknown", review: null };
  }
  if ((session.refs.order_id && incoming.order_id && session.refs.order_id !== incoming.order_id) ||
      (session.refs.intent_id && incoming.intent_id && session.refs.intent_id !== incoming.intent_id)) return base;
  if (session.authoritative === "issued" && !["issued", "paid", "terminal_unpaid"].includes(incoming.state)) return base;
  return { ...base, authoritative: incoming.state, review: incoming.review, refs: {
    order_id: incoming.order_id || session.refs.order_id,
    intent_id: incoming.intent_id || session.refs.intent_id,
  } };
}

export function mayStartAnotherShopRequest(session: Session) {
  return !session.operation && (session.authoritative === "canceled" || session.authoritative === "paid" || session.authoritative === "terminal_unpaid");
}
