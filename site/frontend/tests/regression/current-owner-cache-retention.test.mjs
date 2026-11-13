import test from "node:test";
import assert from "node:assert/strict";
import { sourceRuntime } from "../helpers/source-runtime.mjs";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const owner = "0000000088";
const key = /const KEY = "([^"]+)"/.exec(readFileSync(
  fileURLToPath(new URL("../../src/lib/userDataCache.ts", import.meta.url)), "utf8",
))?.[1];
assert.ok(key, "Personal cache storage key must be present in owner source");
const days = 7 * 24 * 60 * 60 * 1000;
const dataKey = ["panels", owner, "list", "active"];
const oldData = { pages: [{items: [{public_id: "PNL-00000001"}]}], pageParams: [null] };

function configured(runtime) {
  const api = runtime.load("lib/queryClient.ts");
  const client = api.createEfhcQueryClient();
  api.activateUserDataOwner(client, owner, false);
  return {api,client};
}

test("Owner cache retention persists seven days from a genuine app visit, not network polling", () => {
  const storage = new Map(), session = new Map();
  const runtime = sourceRuntime({storage, session});
  const {client} = configured(runtime);
  client.setQueryData(dataKey,oldData);
  const record = JSON.parse(storage.get(key + ":" + owner));
  assert.equal(record.owner,owner);
  assert.ok(Number.isSafeInteger(record.lastHumanVisitAt));
  assert.equal(runtime.load("lib/userDataCache.ts").USER_CACHE_RETENTION_MS,days);
  const visit = record.lastHumanVisitAt;
  client.setQueryData(dataKey,{pages:[{items:[]}],pageParams:[null]});
  assert.equal(JSON.parse(storage.get(key + ":" + owner)).lastHumanVisitAt,visit,
    "automatic successful query cannot extend last-human-visit clock");
  client.clear();
});

test("Expired owner-scoped snapshots are removed from both tab and durable storage", () => {
  const storage = new Map(), session = new Map();
  const runtime = sourceRuntime({storage,session});
  const {client} = configured(runtime);
  client.setQueryData(dataKey,oldData);
  const stale = Date.now() - days - 1;
  for (const storageTarget of [storage,session]) {
    for (const entryKey of [key, key + ":" + owner]) {
      if (!storageTarget.has(entryKey)) continue;
      const entry = JSON.parse(storageTarget.get(entryKey));
      entry.lastHumanVisitAt = stale;
      storageTarget.set(entryKey,JSON.stringify(entry));
    }
  }
  client.clear();
  const next = sourceRuntime({storage,session});
  const {client: recovered} = configured(next);
  assert.equal(recovered.getQueryData(dataKey),undefined);
  assert.equal(storage.has(key+":"+owner),false);
  recovered.clear();
});

test("Same owner may migrate legacy cache on actual open without losing valid offline data", () => {
  const storage = new Map(), session = new Map();
  const runtime = sourceRuntime({storage,session});
  const {client} = configured(runtime);
  client.setQueryData(dataKey,oldData);
  for (const [storageTarget, entryKey] of [[storage,key+":"+owner],[session,key]]) {
    const record = JSON.parse(storageTarget.get(entryKey));
    delete record.lastHumanVisitAt;
    storageTarget.set(entryKey,JSON.stringify(record));
  }
  client.clear();
  const reopened = sourceRuntime({storage,session});
  const {client: restored} = configured(reopened);
  assert.deepEqual(JSON.parse(JSON.stringify(restored.getQueryData(dataKey))),oldData);
  assert.ok(JSON.parse(storage.get(key+":"+owner)).lastHumanVisitAt>0);
  restored.clear();
});

test("A different Global ID cannot restore the previous owner's cached data", () => {
  const storage = new Map(), session = new Map();
  const runtime = sourceRuntime({storage,session});
  const {api,client} = configured(runtime);
  client.setQueryData(dataKey,oldData);
  api.activateUserDataOwner(client,"0000000077",false);
  assert.equal(client.getQueryData(dataKey),undefined);
  client.clear();
});

test("Obsolete withdrawal query shapes cannot break an owner cache warm start", () => {
  const storage = new Map(), session = new Map();
  const runtime = sourceRuntime({storage, session});
  const {client} = configured(runtime);
  const historyKey = ["withdrawals", owner, "balance-history"];
  const listKey = ["withdrawals", owner, "list", "all"];
  const validListKey = ["withdrawals", owner, "list", "PENDING"];
  const validList = {pages: [{items: [], next_cursor: null}], pageParams: [null]};

  client.setQueryData(dataKey, oldData);
  client.setQueryData(validListKey, validList);
  client.setQueryData(historyKey, []);
  client.setQueryData(listKey, {items: []});
  assert.equal(client.getQueryData(listKey).items.length, 0);
  const stored = JSON.parse(storage.get(key + ":" + owner));
  assert.equal(stored.entries.some(entry => JSON.stringify(entry.key) === JSON.stringify(listKey)), false,
    "invalid new query results must not be persisted");

  stored.entries.unshift(
    {key: listKey, data: {items: []}, updatedAt: Date.now()},
    {key: historyKey, data: {items: []}, updatedAt: Date.now()},
  );
  session.set(key, JSON.stringify(stored));
  storage.set(key + ":" + owner, JSON.stringify(stored));
  client.clear();

  const reopened = sourceRuntime({storage, session});
  const {client: restored} = configured(reopened);
  assert.equal(restored.getQueryData(listKey), undefined);
  assert.deepEqual(JSON.parse(JSON.stringify(restored.getQueryData(historyKey))), []);
  assert.deepEqual(JSON.parse(JSON.stringify(restored.getQueryData(validListKey))), validList);
  assert.deepEqual(JSON.parse(JSON.stringify(restored.getQueryData(dataKey))), oldData);
  restored.clear();
});
