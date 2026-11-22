import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { syncSnapshotSchema } from "../services/snapshot.service";
import { balanceHistoryItemSchema } from "../services/profile.service";
import { WithdrawPageResponseSchema } from "./api/generated/economicUserSeamValidators";
import { windowStateStorage } from "./windowState";

const KEY = "EFHC_USER_DATA_CACHE_V1";
const MAX_BYTES = 3_000_000;
// Owner-scoped display snapshots have no calendar TTL; Serwist manages
// only public HTTP resources, not private validated local display snapshots.
// Only display data. Never persist credentials, handoff tokens, permissions or mutations.
const RESOURCES = new Set(["syncSnapshot", "panels", "referrals", "ranks", "exchangePreview", "tasksMy", "tasksEarnings", "profile", "withdrawals"]);
type Entry = {key: QueryKey; data: unknown; updatedAt: number};
type Cache = {owner: string | null; entries: Entry[]};
const controllers = new WeakMap<QueryClient, Cache>();
let settingsOwner: string | null = null;
const validId = (value: unknown): value is string => typeof value === "string" && /^\d{10}$/.test(value) && value !== "0000000000";
const userKey = (key: QueryKey) => RESOURCES.has(String(key[0])) && validId(key[1]);

/** Only restore confirmed withdrawal reads in the format consumed by their query hooks. */
function restorableEntry(entry: Entry): boolean {
  if (!Array.isArray(entry?.key) || !userKey(entry.key)) return false;
  if (entry.key[0] !== "withdrawals") return true;
  if (entry.key[2] === "balance-history") return balanceHistoryItemSchema.array().safeParse(entry.data).success;
  if (entry.key[2] !== "list" || !entry.data || typeof entry.data !== "object") return false;
  const pages = (entry.data as {pages?: unknown}).pages;
  const pageParams = (entry.data as {pageParams?: unknown}).pageParams;
  return Array.isArray(pages) && Array.isArray(pageParams) &&
    pages.length > 0 && pages.length === pageParams.length &&
    pages.every(page => WithdrawPageResponseSchema.safeParse(page).success);
}
const emptyCache = (): Cache => ({owner: null, entries: []});

function decode(raw: string | null): Cache {
  try {
    const value = JSON.parse(raw || "null");
    if (validId(value?.owner) && Array.isArray(value.entries)) {
      // Historical records may contain lastHumanVisitAt. Ignore that field:
      // age-based eviction of personal data was explicitly withdrawn.
      return {
      owner: value.owner,
      entries: value.entries.filter((e: Entry) => restorableEntry(e) && e.key[1] === value.owner && e.data !== undefined && Number.isFinite(e.updatedAt))
        .filter((e: Entry) => e.key[0] !== "syncSnapshot" || (syncSnapshotSchema.safeParse(e.data).success && (e.data as {profile: {global_id: string}}).profile.global_id === value.owner)),
      };
    }
  } catch { /* Storage is optional; it never gates rendering. */ }
  return emptyCache();
}
function read(): Cache {
  const storage = windowStateStorage();
  const raw = storage.getItem(KEY);
  const cache = decode(raw);
  if (raw && !cache.owner) storage.removeItem(KEY);
  return cache;
}
function durable(owner: string): Cache {
  try {
    const key = `${KEY}:${owner}`;
    const raw = window.localStorage.getItem(key);
    const cache = decode(raw);
    if (cache.owner === owner) return cache;
    if (raw) window.localStorage.removeItem(key);
  } catch { /* Optional device persistence may be unavailable. */ }
  return {owner, entries: []};
}
function persist(cache: Cache, publish = true) {
  try {
    const entries: Entry[] = [];
    for (const entry of cache.entries) {
      if (new Blob([JSON.stringify([...entries, entry])]).size <= MAX_BYTES) entries.push(entry);
    }
    const raw = JSON.stringify({owner: cache.owner, entries});
    windowStateStorage().setItem(KEY, raw);
    if (publish && cache.owner && entries.length) window.localStorage.setItem(`${KEY}:${cache.owner}`, raw);
  } catch { /* Keep the current in-memory model if disk storage is unavailable. */ }
}
export function currentUserDataOwner(): string | null {
  return settingsOwner ?? (typeof window === "undefined" ? null : read().owner);
}

export function startUserDataPersistence(client: QueryClient) {
  const cache = read();
  controllers.set(client, cache);
  client.getQueryCache().subscribe(event => {
    if (event.type !== "updated" || event.action.type !== "success") return;
    const query = event.query;
    if (!query || !userKey(query.queryKey) || query.queryKey[1] !== cache.owner) return;
    // A rejected refetch still contains the last confirmed data.
    if (query.state.data === undefined) return;
    if (!restorableEntry({key: query.queryKey, data: query.state.data, updatedAt: query.state.dataUpdatedAt})) return;
    const key = JSON.stringify(query.queryKey);
    cache.entries = [{key: query.queryKey, data: query.state.data, updatedAt: query.state.dataUpdatedAt}, ...cache.entries.filter(e => JSON.stringify(e.key) !== key)];
    persist(cache);
  });
}
export function activateUserCache(client: QueryClient, owner: string | null, admin: boolean): boolean {
  if (admin || !validId(owner)) return false;
  const cache = controllers.get(client);
  if (!cache) return false;
  const changed = cache.owner !== null && cache.owner !== owner;
  if (changed) {
    // OWNER invariant: a Global ID switch invalidates prior display data.
    // Returning to a previous owner requires a new authoritative read.
    cache.entries = [];
    cache.owner = owner;
    settingsOwner = owner;
    persist(cache, false);
    // Removing cancels the old queries, including their fetch AbortSignal.
    client.removeQueries({predicate: q => userKey(q.queryKey)});
  } else {
    // A recovered tab may retain its verified owner marker while its
    // session entry list is empty. Restore the same owner's durable snapshot.
    if (cache.owner === null || (cache.owner === owner && cache.entries.length === 0)) {
      const restored = durable(owner);
      cache.entries = restored.entries;
    }
    cache.owner = owner;
    settingsOwner = owner;
  }
  // Hydrate after removing any foreign-owner queries and before first paint.
  for (const entry of [...cache.entries]) {
    if (client.getQueryData(entry.key) === undefined) client.setQueryData(entry.key, entry.data, {updatedAt: entry.updatedAt});
  }
  persist(cache, !changed);
  return changed;
}

/** An explicit sign-out revokes personal display snapshots. Normal browser
 * reopening does not call this, preserving same-owner offline warm starts. */
export function forgetUserDataOnLogout(client: QueryClient): void {
  const cache = controllers.get(client);
  if (!cache) return;
  const owner = cache.owner;
  cache.owner = null;
  cache.entries = [];
  settingsOwner = null;
  windowStateStorage().removeItem(KEY);
  if (owner) {
    try { window.localStorage.removeItem(`${KEY}:${owner}`); }
    catch { /* Optional storage may be unavailable. */ }
  }
  client.removeQueries({predicate: query => userKey(query.queryKey)});
}
