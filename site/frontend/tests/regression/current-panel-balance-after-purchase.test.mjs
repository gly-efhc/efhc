import test from "node:test";
import assert from "node:assert/strict";
import { sourceRuntime } from "../helpers/source-runtime.mjs";

const OWNER = "0000000088";
const OTHER = "0000000077";
const snapshot = (main, bonus = "0.00000000", owner = OWNER) => ({
  profile: { global_id: owner, main_balance: main, bonus_balance: bonus },
});

function activationHarness({fetchSnapshot, rejectInvalidation = false, owner = OWNER} = {}) {
  const events = [];
  const data = new Map();
  let financialRequests = 0;
  const key = k => JSON.stringify(k);
  const client = {
    invalidateQueries: async ({queryKey, refetchType}) => {
      events.push(["invalidate", queryKey, refetchType ?? "active"]);
      if (rejectInvalidation && refetchType !== "none") throw new Error("cache network error");
    },
    setQueryData: (queryKey, payload) => {
      events.push(["set", queryKey]);
      data.set(key(queryKey), payload);
    },
    getQueryData: queryKey => data.get(key(queryKey)),
  };
  const runtime = sourceRuntime({
    overrides: {
      "@tanstack/react-query": {
        useMutation: options => options,
        useQueryClient: () => client,
      },
      "../auth/AuthSessionProvider": { useAuthOwnerGlobalId: () => owner },
      "../services/panels.service": {
        activatePanel: () => { financialRequests++; throw new Error("not for read-only refresh"); },
      },
      "../services/snapshot.service": {
        fetchSyncSnapshot: async () => {
          events.push(["fetch"]);
          return fetchSnapshot();
        },
      },
    },
  });
  return {
    hook: runtime.load("queries/usePanels.ts").usePanelActivation(),
    client, events,
    get financialRequests() { return financialRequests; },
  };
}

test("After every successful paid panel, server-confirmed balance replaces persisted snapshot", async () => {
  let confirmed = snapshot("417.18000000", "0.00000000");
  const h = activationHarness({fetchSnapshot: () => confirmed});
  const queryKey = ["syncSnapshot", OWNER];
  h.client.setQueryData(queryKey, snapshot("517.18000000"));
  h.events.length = 0;
  await h.hook.onSuccess();
  assert.equal(h.client.getQueryData(queryKey).profile.main_balance, "417.18000000");
  assert.equal(h.events.at(-1)[0], "set");
  assert.equal(h.events.at(-2)[0], "fetch");
  assert.equal(h.events.filter(e => e[0] === "invalidate").length, 3);
  confirmed = snapshot("317.18000000");
  await h.hook.onSuccess();
  assert.equal(h.client.getQueryData(queryKey).profile.main_balance, "317.18000000");
  assert.equal(h.financialRequests, 0, "a post-purchase refresh must never pay again");
});

test("Failed snapshot refresh cannot change a committed panel payment into an error", async () => {
  const h = activationHarness({
    fetchSnapshot: () => { throw new Error("temporarily offline"); },
    rejectInvalidation: true,
  });
  await assert.doesNotReject(h.hook.onSuccess());
  assert.equal(h.financialRequests, 0);
  assert.ok(h.events.some(e => e[0] === "invalidate" && e[2] === "none"));
  assert.equal(h.events.some(e => e[0] === "set"), false);
});

test("A response for a different Global ID never updates the purchasing owner's snapshot", async () => {
  const h = activationHarness({fetchSnapshot: () => snapshot("9999.00000000", "0.00000000", OTHER)});
  await h.hook.onSuccess();
  assert.equal(h.events.some(e => e[0] === "set"), false);
});

test("An unauthenticated owner does not fetch, change cache or invent financial operations", async () => {
  const h = activationHarness({owner: null, fetchSnapshot: () => snapshot("1.00000000")});
  await h.hook.onSuccess();
  assert.equal(h.events.some(e => e[0] === "fetch" || e[0] === "set"), false);
  assert.equal(h.financialRequests, 0);
});

test("A successful kWh exchange updates the shared Header snapshot with server receipt and fresh account data", async () => {
  const owner = OWNER;
  const key = ["syncSnapshot", owner];
  const events = [];
  const state = new Map([[JSON.stringify(key), snapshot("317.18000000")]]);
  let conversionCalls = 0;
  const client = {
    getQueryData: queryKey => state.get(JSON.stringify(queryKey)),
    setQueryData: (queryKey, updater) => {
      const previous = state.get(JSON.stringify(queryKey));
      const value = typeof updater === "function" ? updater(previous) : updater;
      events.push(["set", value?.profile?.main_balance]);
      state.set(JSON.stringify(queryKey), value);
    },
    cancelQueries: async () => events.push(["cancel"]),
    invalidateQueries: async ({queryKey}) => events.push(["invalidate", queryKey]),
  };
  const h = sourceRuntime({
    overrides: {
      "@tanstack/react-query": {useMutation: cfg => cfg, useQueryClient: () => client},
      "../auth/AuthSessionProvider": {useAuthOwnerGlobalId: () => owner},
      "../services/exchange.service": {
        convertExchange: () => {conversionCalls++; throw Error("must not pay on refresh");},
      },
      "../services/snapshot.service": {
        fetchSyncSnapshot: async () => {
          events.push(["fetch"]);
          return snapshot("392.04647293");
        },
      },
    },
  });
  const hook = h.load("queries/useExchange.ts").useExchangeConvert();
  await hook.onSuccess({new__main__balance: "390.00000000", new_available_kwh: "0.00000000"});
  assert.deepEqual(events.filter(e => e[0] === "set").map(e => e[1]), ["390.00000000", "392.04647293"]);
  assert.equal(client.getQueryData(key).profile.main_balance, "392.04647293");
  assert.equal(conversionCalls, 0);
});

test("Failed exchange refresh retains the confirmed receipt, not the stale Header balance", async () => {
  const key = ["syncSnapshot", OWNER];
  const state = new Map([[JSON.stringify(key), snapshot("317.18000000")]]);
  const client = {
    getQueryData: q => state.get(JSON.stringify(q)),
    setQueryData: (q, updater) => {
      const previous = state.get(JSON.stringify(q));
      state.set(JSON.stringify(q), typeof updater === "function" ? updater(previous) : updater);
    },
    cancelQueries: async () => {},
    invalidateQueries: async ({refetchType}) => { if (refetchType !== "none") throw Error("cache blocked"); },
  };
  const h = sourceRuntime({
    overrides: {
      "@tanstack/react-query": {useMutation: opts => opts, useQueryClient: () => client},
      "../auth/AuthSessionProvider": {useAuthOwnerGlobalId: () => OWNER},
      "../services/exchange.service": {convertExchange: () => {throw Error("must not pay on read");}},
      "../services/snapshot.service": {fetchSyncSnapshot: async () => {throw Error("offline");}},
    },
  });
  await assert.doesNotReject(h.load("queries/useExchange.ts").useExchangeConvert().onSuccess({
    new__main__balance: "392.04647293", new_available_kwh: "5.00000000",
  }));
  assert.equal(client.getQueryData(key).profile.main_balance, "392.04647293");
  assert.equal(client.getQueryData(key).profile.available_kwh, "5.00000000");
});
