import type { QueryClient, QueryKey } from "@tanstack/react-query";

const STORAGE_KEY = "efhc_public_catalog_queries_v1";
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
const MAX_BYTES = 3_000_000;
const SAFE_PREFIX = "public-static";

type StoredEntry = {
  data: unknown;
  key: QueryKey;
  updatedAt: number;
};

function isSafeKey(key: QueryKey): boolean {
  return Array.isArray(key) && (
    key[0] === SAFE_PREFIX ||
    (key.length === 1 && key[0] === "tasksCatalog") ||
    (key.length === 2 && key[0] === "browser-shop" && key[1] === "catalog")
  );
}

function readEntries(): StoredEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY) || "[]";
    const value = JSON.parse(raw) as unknown;
    if (!Array.isArray(value)) return [];
    const now = Date.now();
    return value.filter((entry): entry is StoredEntry => {
      if (!entry || typeof entry !== "object") return false;
      const item = entry as StoredEntry;
      return (
        isSafeKey(item.key) &&
        Number.isFinite(item.updatedAt) &&
        now - item.updatedAt <= MAX_AGE_MS
      );
    });
  } catch {
    return [];
  }
}

function writeEntries(entries: StoredEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    const sorted = [...entries].sort(
      (left, right) => right.updatedAt - left.updatedAt,
    );
    let selected: StoredEntry[] = [];
    for (const entry of sorted) {
      const candidate = [...selected, entry];
      const text = JSON.stringify(candidate);
      if (new Blob([text]).size > MAX_BYTES) break;
      selected = candidate;
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(selected),
    );
  } catch {
    // Public catalogue persistence is best effort only.
  }
}

export function hydratePublicCatalogQueries(
  client: QueryClient,
): void {
  for (const entry of readEntries()) {
    client.setQueryData(entry.key, entry.data, {
      updatedAt: entry.updatedAt,
    });
  }
}

export function startPublicCatalogPersistence(
  client: QueryClient,
): () => void {
  if (typeof window === "undefined") return () => undefined;
  let queued = false;
  const flush = () => {
    queued = false;
    const entries = client
      .getQueryCache()
      .getAll()
      .filter((query) => isSafeKey(query.queryKey))
      .filter((query) => query.state.status === "success")
      .map((query) => ({
        key: query.queryKey,
        data: query.state.data,
        updatedAt: query.state.dataUpdatedAt || Date.now(),
      }));
    writeEntries(entries);
  };
  return client.getQueryCache().subscribe((event) => {
    if (!event?.query || !isSafeKey(event.query.queryKey)) return;
    if (queued) return;
    queued = true;
    window.setTimeout(flush, 120);
  });
}
