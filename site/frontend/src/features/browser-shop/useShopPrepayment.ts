import { useEffect, useRef, useState } from "react";
import { getAuthAuthorizationHeader } from "../../lib/auth-session";
import { callShopPrepayment, type PrepareSelection } from "../../services/browserShopPrepayment.service";
import {
  acceptShopReply, mayStartAnotherShopRequest, openShopSession, planShopAction,
  restoreShopSession, showShopModal, type ShopAction,
} from "./shopCheckoutLifecycle";

type Marker = { key: string; scope: string; finalAction: "pay" | "cancel" | null };
type Session = ReturnType<typeof openShopSession>;
const PREFIX = "efhc.shop.request.v1.";
const SALT = PREFIX + "salt";
const UUID = /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/;
const HASH = /^[a-f\d]{64}$/;
function nonce() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  return Array.from(bytes, (v, i) => ([4,6,8,10].includes(i) ? "-" : "") + v.toString(16).padStart(2,"0")).join("");
}
async function tag(value: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2,"0")).join("");
}
function write(key: string, data: string) {
  localStorage.setItem(key, data);
  if (localStorage.getItem(key) !== data) throw new Error("SHOP_PREPAYMENT_STORAGE_REQUIRED");
}
async function slot(owner: string) {
  if (!/^\d{10}$/.test(owner)) throw new Error("SHOP_PREPAYMENT_OWNER_REQUIRED");
  let salt = localStorage.getItem(SALT);
  if (salt === null) { salt = nonce(); write(SALT, salt); }
  if (!UUID.test(salt)) throw new Error("SHOP_PREPAYMENT_STORAGE_INVALID");
  return { key: PREFIX + await tag(JSON.stringify([salt, owner])), salt };
}
function read(key: string): Marker | null {
  const raw = localStorage.getItem(key);
  if (raw === null) return null;
  const value = JSON.parse(raw) as Marker;
  if (!value || !UUID.test(value.key) || !HASH.test(value.scope) ||
      ![null, "pay", "cancel"].includes(value.finalAction)) throw new Error("SHOP_PREPAYMENT_STORAGE_INVALID");
  return value;
}
async function browserLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator.locks?.request !== "function") return fn();
  return await navigator.locks.request(PREFIX, fn);
}

/** This is not a queued payment. The only persisted fields are opaque key/scope/fence. */
export function useShopPrepayment(enabled: boolean, owner: string, token: string, visible: boolean, selected: PrepareSelection | null) {
  const current = useRef<Session | null>(null);
  const executing = useRef(false);
  const context = useRef({ owner, token, visible, enabled });
  context.current = { owner, token, visible, enabled };
  const [session, setSession] = useState<Session | null>(null);
  const selectionInput = selected ? JSON.stringify(selected) : "";
  const [matchingSelection, setMatchingSelection] = useState<{key: string; input: string; owner: string} | null>(null);
  const publish = (next: Session | null) => { current.current = next; setSession(next); };

  useEffect(() => {
    let stale = false;
    publish(null);
    if (!enabled || !owner || !token) return;
    void browserLock(async () => {
      const ownerSlot = await slot(owner);
      const marker = read(ownerSlot.key);
      if (!marker || stale || context.current.owner !== owner || context.current.token !== token) return;
      const restored = restoreShopSession(marker.key, marker.finalAction);
      const { session: waiting, command } = planShopAction(restored, "status", { explicit:false });
      if (!command || executing.current) return;
      publish(waiting);
      let reply;
      try { reply = await callShopPrepayment("status",token,marker.key); } catch { reply = null; }
      if (stale || context.current.owner !== owner || context.current.token !== token ||
          current.current?.operation !== command) return;
      const next = acceptShopReply(waiting,command,reply);
      if (mayStartAnotherShopRequest(next) && read(ownerSlot.key)?.key === marker.key) localStorage.removeItem(ownerSlot.key);
      publish(next);
    }).catch(() => { /* Fail closed if the browser cannot read/verify the marker. */ });
    return () => { stale = true; };
  }, [enabled, owner, token]);

  const reviewKey = session?.authoritative === "prepared" && session.review ? session.key : "";
  useEffect(() => {
    let stale = false;
    setMatchingSelection(null);
    if (!enabled || !owner || !visible || !selectionInput || !reviewKey) return;
    void (async () => {
      const ownerSlot = await slot(owner);
      const marker = read(ownerSlot.key);
      if (!marker || marker.key !== reviewKey) return;
      const scope = await tag(JSON.stringify([ownerSlot.salt, JSON.parse(selectionInput)]));
      if (!stale && scope === marker.scope) setMatchingSelection({ key: reviewKey, input: selectionInput, owner });
    })().catch(() => { /* No price authority without the matching marker. */ });
    return () => { stale = true; };
  }, [enabled, owner, visible, selectionInput, reviewKey]);
  const review = matchingSelection?.key === reviewKey && matchingSelection?.input === selectionInput &&
    matchingSelection?.owner === owner ? session?.review ?? null : null;

  const run = async (action: ShopAction, selection?: PrepareSelection) => {
    if (!enabled || !owner || !token || executing.current) return null;
    executing.current = true;
    try {
      const claim = await browserLock(async () => {
        if (context.current.owner !== owner || context.current.token !== token || !context.current.enabled ||
            (action !== "status" && !context.current.visible)) return null;
        const ownerSlot = await slot(owner);
        let marker = read(ownerSlot.key);
        const selectionTag = selection ? await tag(JSON.stringify([ownerSlot.salt,selection])) : "";
        const fresh = marker === null;
        if (fresh && action === "prepare" && selectionTag) marker = { key: nonce(), scope: selectionTag, finalAction: null };
        if (!marker || (action !== "status" && selectionTag !== marker.scope)) return null;
        const restored = current.current?.key === marker.key ? current.current
          : fresh ? openShopSession(marker.key) : restoreShopSession(marker.key,marker.finalAction);
        const state = showShopModal(restored,context.current.visible);
        if (action === "pay" && (!review || state.review?.review_id !== review.review_id ||
            (selection?.method === "EFHC" && !getAuthAuthorizationHeader()))) return null;
        // The durable fence also blocks a stale PREPARED window in another tab.
        if (marker.finalAction && action !== "status") return null;
        const { session: waiting, command } = planShopAction(state, action, {
          explicit: true, freshUndispatched: fresh, wirePayVerified: true,
        });
        if (!command) return null;
        write(ownerSlot.key,JSON.stringify({ ...marker, finalAction: waiting.dispatchedFinalAction }));
        publish(waiting);
        return { ownerSlot, marker, waiting, command };
      });
      if (!claim) return null;
      let reply: Awaited<ReturnType<typeof callShopPrepayment>> | null = null;
      try { reply = await callShopPrepayment(action,token,claim.marker.key,selection,claim.waiting.review); }
      finally {
        await browserLock(async () => {
          const next = acceptShopReply(claim.waiting,claim.command,reply);
          if (mayStartAnotherShopRequest(next) && read(claim.ownerSlot.key)?.key === claim.marker.key) {
            localStorage.removeItem(claim.ownerSlot.key);
          }
          if (context.current.owner === owner && context.current.token === token) publish(next);
        });
      }
      // A response from the previous identity may still update its own marker,
      // but cannot start any wallet operation in the newly selected account.
      return context.current.owner === owner && context.current.token === token ? reply : null;
    } finally { executing.current = false; }
  };
  return { session, review, run };
}
