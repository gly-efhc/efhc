import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { syncSnapshotSchema } from "../services/snapshot.service";
import { windowStateStorage } from "./windowState";

const KEY = "EFHC_USER_DATA_CACHE_V1";
const MAX_BYTES = 3_000_000;
// Only display data. Never persist credentials, handoff tokens, permissions or mutations.
const RESOURCES = new Set(["syncSnapshot", "panels", "referrals", "ranks", "exchangePreview", "tasksMy", "tasksEarnings", "profile", "withdrawals"]);
type Entry = {key: QueryKey; data: unknown; updatedAt: number};
type Cache = {owner: string | null; entries: Entry[]};
const controllers = new WeakMap<QueryClient, Cache>();
let settingsOwner: string | null = null;
const validId = (value: unknown): value is string => typeof value === "string" && /^\d{10}$/.test(value) && value !== "0000000000";
const userKey = (key: QueryKey) => RESOURCES.has(String(key[0])) && validId(key[1]);

function decode(raw: string | null): Cache {
  try {
    const value = JSON.parse(raw || "null");
    if (validId(value?.owner) && Array.isArray(value.entries)) return {
      owner: value.owner,
      entries: value.entries.filter((e: Entry) => Array.isArray(e?.key) && userKey(e.key) && e.key[1] === value.owner && e.data !== undefined && Number.isFinite(e.updatedAt))
        .filter((e: Entry) => e.key[0] !== "syncSnapshot" || (syncSnapshotSchema.safeParse(e.data).success && (e.data as {profile: {global_id: string}}).profile.global_id === value.owner)),
    };
  } catch { /* Storage is optional; it never gates rendering. */ }
  return {owner: null, entries: []};
}
function read(): Cache { return decode(windowStateStorage().getItem(KEY)); }
function durable(owner: string): Cache {
  try { const cache = decode(window.localStorage.getItem(`${KEY}:${owner}`)); return cache.owner === owner ? cache : {owner, entries: []}; }
  catch { return {owner, entries: []}; }
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
    // Another owner may have a valid disk snapshot from an earlier session.
    // Restore only that owner's display data; never reuse the old owner.
    cache.entries = durable(owner).entries;
    cache.owner = owner;
    settingsOwner = owner;
    persist(cache, false);
    // Removing cancels the old queries, including their fetch AbortSignal.
    client.removeQueries({predicate: q => userKey(q.queryKey)});
  } else {
    if (cache.owner === null) cache.entries = durable(owner).entries;
    cache.owner = owner;
    settingsOwner = owner;
  }
  // Hydrate after removing any foreign-owner queries and before first paint.
  for (const entry of [...cache.entries]) {
    if (client.getQueryData(entry.key) === undefined) client.setQueryData(entry.key, entry.data, {updatedAt: entry.updatedAt});
  }
  persist(cache, false);
  return changed;
}
