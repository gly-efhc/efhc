import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
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
    {key: historyKey, data: [null], updatedAt: Date.now()},
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


test("Withdrawal page retains its actual form with populated and malformed read caches", () => {
  const LayoutContext = React.createContext({});
  const validHistory = [{
    id: "19", amount_efhc: "10.00000000", direction: "debit",
    balance_type: "main", reason: "withdraw_hold", created_at: "2026-11-13T00:00:00Z",
  }];
  const validItems = [{
    id: "9007199254740993", global_id: owner, amount: "10.00000000",
    status: "PENDING", created_at: "2026-11-13T00:00:00Z",
    updated_at: "2026-11-13T00:00:00Z",
  }];
  let withdrawals = {pages: [{items: validItems, next_cursor: null}], pageParams: [null]};
  let history = validHistory;
  const emptyMutation = {isPending: false, error: null, mutateAsync: async () => undefined};
  const query = (data) => ({
    data, isLoading: false, isFetching: false, error: null,
    hasNextPage: false, isFetchNextPageError: false,
    isFetchingNextPage: false, refetch: async () => undefined,
  });
  const t = (value) => value;
  const runtime = sourceRuntime({overrides: {
    "../components/Layout": {LayoutContext},
    "../auth/AuthSessionProvider": {useAuthOwnerGlobalId: () => owner},
    "../hooks/useT": {useT: () => t},
    "../../hooks/useT": {useT: () => t},
    "../hooks/useInterfaceVariantSurface": {
      useInterfaceVariantSurface: () => ({ref: null, handlers: {}, variant: "WD-01"}),
    },
    "../hooks/useOwnerDraft": {useOwnerDraft: (_name, initial) => [initial, () => undefined]},
    "../hooks/useWalletsMe": {useWalletsMe: () => ({
      data: {wallets: [{
        id: "11", wallet_address: "EQ123456789012345678901234",
        is_primary: true, is_active: true,
      }]},
    })},
    "../queries/useWithdrawals": {
      useWithdrawalsPage: () => query(withdrawals),
      useWalletBalanceHistory: () => query(history),
      useCreateWithdrawRequest: () => emptyMutation,
      useCancelWithdrawRequest: () => emptyMutation,
    },
    "../queries/useProfile": {useProfileHistoryExport: () => emptyMutation},
    "../lib/ads/AdManager": {
      AdManager: {runRewardedAd: async () => ({session: {rewarded: false}})},
      adManagerErrorCode: () => "NO_FILL",
    },
  }});
  const Page = runtime.load("pages/withdraw.tsx").default;
  const snap = {profile: {main_balance: "801.00000000"}};
  const layout = {
    t, lang: "ru", settings: {haptics_enabled: false},
    confirm: async () => false, openWalletConnect: () => undefined,
    toast: () => undefined,
  };
  const render = () => renderToStaticMarkup(React.createElement(
    LayoutContext.Provider, {value: layout}, React.createElement(Page, {snap}),
  ));
  const complete = render();
  assert.match(complete, /data-public-surface="withdraw"/);
  assert.match(complete, /801\.00000000 EFHCm/);
  assert.match(complete, /9007199254740993/);
  assert.match(complete, /10\.00000000/);
  withdrawals = {pages: {items: validItems}};
  history = {items: validHistory};
  const recovered = render();
  assert.match(recovered, /data-public-surface="withdraw"/);
  assert.match(recovered, /801\.00000000 EFHCm/);
  assert.doesNotMatch(recovered, /9007199254740993/);
});
