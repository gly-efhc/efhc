import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { sourceRuntime } from "../helpers/source-runtime.mjs";

const SRC = fileURLToPath(new URL("../../src/", import.meta.url));
const read = file => readFileSync(path.join(SRC, file), "utf8");
const owner = "0000000088";
const other = "0000000077";
const cached = (main="517.18000000", bonus="2.18000000", id=owner) => ({
  profile: {global_id:id, main_balance:main, bonus_balance:bonus, username:"owner"},
  panels: {active_count:2},
});
const confirmed = (main="392.04647293", bonus="0.00000000", id=owner) => ({
  global_id:id, main_balance:main, bonus_balance:bonus,
});

test("A stale PWA Header and Balance card are replaced by independent signed account truth",()=>{
  const h=sourceRuntime();
  const {overlayVerifiedAccountBalances: overlay}=h.load("lib/accountBalancePresentation.ts");
  const original=cached(), next=overlay(original,confirmed(),owner,1_000,2_000);
  assert.equal(next.profile.main_balance,"392.04647293");
  assert.equal(next.profile.bonus_balance,"0.00000000");
  assert.equal(next.profile.username,"owner");
  assert.equal(next.panels.active_count,2);
  assert.equal(original.profile.main_balance,"517.18000000");
});
test("A more recent mutation receipt or new synchronized snapshot always beats an older account read",()=>{
  const h=sourceRuntime(), {overlayVerifiedAccountBalances: overlay}=h.load("lib/accountBalancePresentation.ts");
  const fresh=cached("396.00000000","0.00000000");
  assert.equal(overlay(fresh,confirmed(),owner,5_000,4_000),fresh);
  assert.equal(overlay(fresh,confirmed(),owner,5_000,5_000),fresh);
});
test("Account verification blocks another owner, unauthenticated state, and invalid timestamp",()=>{
  const h=sourceRuntime(), {overlayVerifiedAccountBalances: overlay}=h.load("lib/accountBalancePresentation.ts");
  const original=cached();
  for(const [bal,id,stamp] of [[confirmed("1000","0",other),owner,2_000],[confirmed(),other,2_000],[confirmed(),null,2_000],[confirmed(),owner,0]]) {
    assert.equal(overlay(original,bal,id,1_000,stamp),original);
  }
});
test("GET /user/me parses nonnegative D8 financial truth and rejects invalid or misowned payloads",async()=>{
  let payload={...confirmed(),username:"ignored"};
  const h=sourceRuntime({overrides:{"../lib/api":{apiRequest:async(route,verb)=>{
    assert.equal(route,"/user/me");assert.equal(verb,"GET");return payload;
  }}}});
  const svc=h.load("services/accountBalance.service.ts");
  assert.equal((await svc.readCurrentAccountBalances()).main_balance,"392.04647293");
  payload={...confirmed(),bonus_balance:"not-a-number"};
  await assert.rejects(svc.readCurrentAccountBalances());
});
test("Authenticated owner GET revalidates on every mount/focus/reconnect without replaying a mutation",async()=>{
  let calls=0;
  const options=[];
  const h=sourceRuntime({overrides:{
    "@tanstack/react-query":{useQuery:cfg=>{options.push(cfg);return cfg;}},
    "../auth/AuthSessionProvider":{
      useAuthOwnerGlobalId:()=>owner,
      useAuthSessionController:()=>({status:"authenticated"}),
    },
    "../services/accountBalance.service":{readCurrentAccountBalances:async()=>{
      calls++;return confirmed();
    }},
  }});
  const hook=h.load("hooks/useCurrentAccountBalances.ts").useCurrentAccountBalances();
  assert.equal(hook.enabled,true);
  assert.equal(hook.refetchOnMount,"always");
  assert.equal(hook.refetchOnWindowFocus,"always");
  assert.equal(hook.refetchOnReconnect,"always");
  assert.equal(hook.refetchInterval,30_000);
  assert.equal((await hook.queryFn({signal:undefined})).main_balance,"392.04647293");
  assert.equal(calls,1);
  assert.deepEqual([...hook.queryKey],["accountBalance",owner]);
  const app=read("pages/_app.tsx");
  assert.match(app,/overlayVerifiedAccountBalances\(/);
  assert.match(app,/currentAccountBalances\.dataUpdatedAt/);
  assert.match(app,/snapshotUpdatedAt/);
  assert.match(app,/const visibleSnap = useMemo\(/);
  const layout=read("components/Layout.tsx");
  assert.match(layout,/mainBalance=\{props\.snapshot\?\.profile\?\.main_balance/);
  assert.match(layout,/bonusBalance=\{props\.snapshot\?\.profile\?\.bonus_balance/);
  const profile=read("features/profile/WebProfilePage.tsx");
  assert.match(profile,/const main = readAmount\(profile\.main_balance\)/);
  assert.match(profile,/const bonus = readAmount\(profile\.bonus_balance\)/);
});
test("Authenticated GET is not persisted as a historical monetary balance, and activity remains active",()=>{
  const cache=read("lib/userDataCache.ts"),activity=read("lib/frontendActivity.ts");
  assert.doesNotMatch(cache,/RESOURCES = new Set\([^\n]*"accountBalance"/);
  assert.match(activity,/client\.refetchQueries/);
  assert.match(read("queries/usePanels.ts"),/queryKeys\.account\.current\(globalId\)/);
  assert.match(read("queries/useExchange.ts"),/queryKeys\.account\.current\(globalId\)/);
});
