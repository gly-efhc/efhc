import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { sourceRuntime } from "../helpers/source-runtime.mjs";

test("Ad daily-limit cache survives restart, isolates Global ID and resets on UTC date", () => {
  const disk = new Map();
  const h = sourceRuntime({storage:disk});
  const c = h.load("lib/ads/dailyLimitCache.ts");
  const owner = "0000000088", second = "0000000077";
  const day = Date.parse("2026-11-10T23:59:59Z");
  c.writeAdDailyLimits(owner, new Set(["AD_A", "AD_B"]), day);
  assert.deepEqual([...c.readAdDailyLimits(owner,day)],["AD_A","AD_B"]);
  assert.deepEqual([...c.readAdDailyLimits(second,day)],[]);
  assert.deepEqual([...c.readAdDailyLimits(owner,day+1000)],[]);
  const reloaded = sourceRuntime({storage:disk}).load("lib/ads/dailyLimitCache.ts");
  assert.deepEqual([...reloaded.readAdDailyLimits(owner,day)],["AD_A","AD_B"]);
});
test("Tasks only persist display limits, never replay reward requests offline",()=>{
  const tasks=readFileSync(fileURLToPath(new URL("../../src/pages/tasks.tsx",import.meta.url)),"utf8");
  assert.match(tasks,/DAILY_LIMIT_REACHED/);
  assert.match(tasks,/writeAdDailyLimits\(globalId, next\)/);
  assert.match(tasks,/readAdDailyLimits\(globalId\)/);
  const cache=readFileSync(fileURLToPath(new URL("../../src/lib/ads/dailyLimitCache.ts",import.meta.url)),"utf8");
  assert.doesNotMatch(cache,/reward_efhcb|bonus_balance|private_key|wallet_seed/);
});
