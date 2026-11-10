import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { syncSnapshotSchema } from "../services/snapshot.service";
import { windowStateStorage } from "./windowState";

const KEY = "EFHC_USER_DATA_CACHE_V1";
const MAX_BYTES = 3_000_000;
// Production owner display data expires after seven days without a human visit.
// Network polling or successful query refetches never extend this clock.
export const USER_CACHE_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;
const VISIT_WRITE_INTERVAL_MS = 15 * 60 * 1000;
// Only display data. Never persist credentials, handoff tokens, permissions or mutations.
const RESOURCES = new Set(["syncSnapshot", "panels", "referrals", "ranks", "exchangePreview", "tasksMy", "tasksEarnings", "profile", "withdrawals"]);
type Entry = {key: QueryKey; data: unknown; updatedAt: number};
type Cache = {owner: string | null; entries: Entry[]; lastHumanVisitAt: number | null};
const controllers = new WeakMap<QueryClient, Cache>();
let settingsOwner: string | null = null;
const validId = (value: unknown): value is string => typeof value === "string" && /^\d{10}$/.test(value) && value !== "0000000000";
const userKey = (key: QueryKey) => RESOURCES.has(String(key[0])) && validId(key[1]);
const emptyCache = (): Cache => ({owner: null, entries: [], lastHumanVisitAt: null});

function decode(raw: string | null): Cache {
  try {
    const value = JSON.parse(raw || "null");
    if (validId(value?.owner) && Array.isArray(value.entries)) {
      // Legacy cache records have no visit marker. Preserve once and migrate
      // only when this owner actually opens the app, without faking activity
      // on background financial polls.
      const present = Object.prototype.hasOwnProperty.call(value, "lastHumanVisitAt");
      const visit = value.lastHumanVisitAt;
      const now = Date.now();
      if (present && (
        !Number.isSafeInteger(visit) || visit <= 0 || visit > now ||
        now - visit >= USER_CACHE_RETENTION_MS
      )) return emptyCache();
      return {
      owner: value.owner,
      lastHumanVisitAt: present ? visit : null,
      entries: value.entries.filter((e: Entry) => Array.isArray(e?.key) && userKey(e.key) && e.key[1] === value.owner && e.data !== undefined && Number.isFinite(e.updatedAt))
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
  return {owner, entries: [], lastHumanVisitAt: null};
}
function persist(cache: Cache, publish = true) {
  try {
    const entries: Entry[] = [];
    for (const entry of cache.entries) {
      if (new Blob([JSON.stringify([...entries, entry])]).size <= MAX_BYTES) entries.push(entry);
    }
    const raw = JSON.stringify({owner: cache.owner, entries, lastHumanVisitAt: cache.lastHumanVisitAt});
    windowStateStorage().setItem(KEY, raw);
    if (publish && cache.owner && entries.length) window.localStorage.setItem(`${KEY}:${cache.owner}`, raw);
  } catch { /* Keep the current in-memory model if disk storage is unavailable. */ }
}
export function currentUserDataOwner(): string | null {
  return settingsOwner ?? (typeof window === "undefined" ? null : read().owner);
}

/** Human interaction extends the retention period; server polling does not. */
export function recordUserCacheVisit(client: QueryClient, atMs = Date.now()): void {
  const cache = controllers.get(client);
  if (!cache || !validId(cache.owner) || !Number.isSafeInteger(atMs)) return;
  if (cache.lastHumanVisitAt !== null &&
      atMs - cache.lastHumanVisitAt < VISIT_WRITE_INTERVAL_MS) return;
  cache.lastHumanVisitAt = atMs;
  persist(cache);
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
    cache.lastHumanVisitAt = null;
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
      cache.lastHumanVisitAt = restored.lastHumanVisitAt;
    }
    cache.owner = owner;
    settingsOwner = owner;
  }
  // Actual app entry counts as a human visit; network-only updates do not.
  // Refresh the owner-scoped local timestamp while keeping persisted snapshot
  // values untouched until the next authoritative read.
  cache.lastHumanVisitAt = Date.now();
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
  cache.lastHumanVisitAt = null;
  settingsOwner = null;
  windowStateStorage().removeItem(KEY);
  if (owner) {
    try { window.localStorage.removeItem(`${KEY}:${owner}`); }
    catch { /* Optional storage may be unavailable. */ }
  }
  client.removeQueries({predicate: query => userKey(query.queryKey)});
}
