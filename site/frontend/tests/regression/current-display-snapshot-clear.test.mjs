import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {readAdminDisplay, clearAdminDisplaySnapshots} from "../../src/lib/adminReadCache.ts";
import {clearPublicCatalogSnapshots, startPublicCatalogPersistence} from "../../src/lib/publicCatalogPersistence.ts";

function storage() {
  const m = new Map();
  return { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: k => m.delete(k) };
}

test("Admin clears only display data and fences a pre-clear result", async () => {
  const localStorage = storage();
  globalThis.window = {localStorage};
  localStorage.setItem("admin-session", "keep");
  await readAdminDisplay("owner", "/admin/ui", async () => "initial");
  let resolve;
  const stale = readAdminDisplay("owner", "/admin/ui", () => new Promise(r => { resolve = r; }));
  const rejection = assert.rejects(stale, /ADMIN_DISPLAY_CLEARED/);
  clearAdminDisplaySnapshots();
  resolve("must not persist");
  await rejection;
  assert.equal(localStorage.getItem("EFHC_ADMIN_READ_CACHE_V1:owner"), null);
  assert.equal(localStorage.getItem("admin-session"), "keep");
  await readAdminDisplay("owner", "/admin/ui", async () => "fresh read permitted");
  assert.equal(JSON.parse(localStorage.getItem("EFHC_ADMIN_READ_CACHE_V1:owner")).values["/admin/ui"], "fresh read permitted");
});

test("public clear is allowlisted, and queued persistence cannot resurrect removed queries", async () => {
  const localStorage = storage(), timers = [];
  globalThis.window = {localStorage, setTimeout: f => timers.push(f)};
  localStorage.setItem("efhc_public_catalog_queries_v1", "[]");
  localStorage.setItem("checkout-draft", "keep");
  const query = queryKey => ({queryKey, state: {status: "success", data: "snapshot", dataUpdatedAt: 1}});
  let qs = [["public-static", "x"], ["tasksCatalog"], ["browser-shop", "catalog"], ["browser-shop", "draft"], ["other"]].map(query);
  let listener;
  const client = {
    cancelQueries: async ({predicate}) => assert.equal(qs.filter(predicate).length, 3),
    removeQueries: ({predicate}) => {qs = qs.filter(q => !predicate(q));},
    getQueryCache: () => ({getAll: () => qs, subscribe: f => {listener = f;}}),
  };
  startPublicCatalogPersistence(client);
  listener({query: qs[0]});
  await clearPublicCatalogSnapshots(client);
  timers.forEach(f => f());
  assert.equal(localStorage.getItem("efhc_public_catalog_queries_v1"), null);
  assert.equal(localStorage.getItem("checkout-draft"), "keep");
  assert.deepEqual(qs.map(q => q.queryKey), [["browser-shop", "draft"], ["other"]]);
});

test("USER clears only current-owner display queries and preserves identity marker", () => {
  const src = readFileSync(new URL("../../src/lib/userDataCache.ts", import.meta.url), "utf8")
    .split("export function clearUserDisplaySnapshots")[1];
  assert.match(src, /userKey\(query.queryKey\) && query.queryKey\[1\] === owner/);
  assert.match(src, /JSON.stringify\(\{owner, entries: \[\]\}\)/);
  assert.match(src, /removeItem\(`\$\{KEY\}:\$\{owner\}`\)/);
  assert.doesNotMatch(src, /settingsOwner\s*=|cache.owner\s*=\s*null|forgetUserDataOnLogout|\.clear\(\)/);
});
