/** Read-only Admin presentation cache. A cached view never approves a command. */
const KEY = "EFHC_ADMIN_READ_CACHE_V1";
let activeOwner: string | null = null;
let values: Record<string, unknown> = {};
let generation = 0;
const cacheable = (path: string) => path.startsWith("/admin/") && !/\/(access|auth|roles|permissions|secrets|handoff)(\/|\?|$)/.test(path);

export async function readAdminDisplay<T>(owner: string | null, path: string, fetchConfirmed: () => Promise<T>): Promise<T> {
  if (!owner || !cacheable(path)) return fetchConfirmed();
  if (activeOwner !== owner) {
    activeOwner = owner; values = {};
    try {
      const cached = JSON.parse(window.localStorage.getItem(`${KEY}:${owner}`) || "null");
      if (cached?.owner === owner && cached.values && typeof cached.values === "object" && !Array.isArray(cached.values)) values = cached.values;
    } catch { /* Disk failure cannot remove an Admin page. */ }
  }
  const requestedGeneration = generation;
  try {
    const data = await fetchConfirmed();
    if (activeOwner !== owner) throw new Error("ADMIN_READ_OWNER_CHANGED");
    if (requestedGeneration !== generation) throw new Error("ADMIN_DISPLAY_CLEARED");
    values[path] = data;
    try {
      const serialized = JSON.stringify({owner, values});
      if (new Blob([serialized]).size <= 3_000_000) window.localStorage.setItem(`${KEY}:${owner}`, serialized);
    } catch { /* Keep the current in-memory view. */ }
    return data;
  } catch (error) {
    const status = (error as {status?: number} | null)?.status;
    if (activeOwner !== owner || requestedGeneration !== generation || status === 401 || status === 403) throw error;
    if (Object.prototype.hasOwnProperty.call(values, path)) return values[path] as T;
    throw error;
  }
}

/** Keep the owner context; invalidate pre-clear reads before touching disk. */
export function clearAdminDisplaySnapshots(): void {
  generation++;
  values = {};
  if (activeOwner && typeof window !== "undefined") window.localStorage.removeItem(`${KEY}:${activeOwner}`);
}
