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
