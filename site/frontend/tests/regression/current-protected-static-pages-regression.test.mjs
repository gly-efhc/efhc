import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// OWNER invariant: pages remain present when API/auth/Global ID fails.
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const protectedPages = [
  "_app.tsx",
  "_document.tsx",
  "admin/ads.tsx",
  "admin/api-workbench.tsx",
  "admin/bank.tsx",
  "admin/bonuses.tsx",
  "admin/diagnostics.tsx",
  "admin/efhc-deposits.tsx",
  "admin/emergency.tsx",
  "admin/hub.tsx",
  "admin/index.tsx",
  "admin/logs.tsx",
  "admin/panels.tsx",
  "admin/referrals.tsx",
  "admin/reports.tsx",
  "admin/sale-packages.tsx",
  "admin/shop.tsx",
  "admin/system.tsx",
  "admin/tasks.tsx",
  "admin/user-history.tsx",
  "admin/users.tsx",
  "admin/vip-nft.tsx",
  "admin/withdrawals.tsx",
  "ads.tsx",
  "api/public-runtime-config.ts",
  "api/tonconnect-manifest.ts",
  "app.tsx",
  "browser-shop.tsx",
  "browser-shop/orders.tsx",
  "browser-shop/profile.tsx",
  // Legacy public TEST console retired; all active Admin routes remain protected.
  "exchange.tsx",
  "faq.tsx",
  "hub.tsx",
  "index.tsx",
  "panels.tsx",
  "panels/portfolio.tsx",
  "ranks.tsx",
  "referrals.tsx",
  "referrals/active.tsx",
  "referrals/inactive.tsx",
  "referrals/my.tsx",
  "support.tsx",
  "tasks.tsx",
  "web-profile.tsx",
  "withdraw.tsx"
];

test("all OWNER-protected React pages exist independent of backend state", () => {
  for (const page of protectedPages) {
    assert.ok(existsSync(resolve(frontend, "src/pages", page)), "Missing protected page: "+page);
  }
});

test("backend/auth failure must not redirect away from a protected Admin route", () => {
  const source = readFileSync(resolve(frontend, "src/pages/_app.tsx"), "utf8");
  assert.doesNotMatch(source, /void router\.replace\((["'])\/\1\)/);
  // Public TEST must not bypass live server authorization for Admin routes.
  assert.doesNotMatch(source, /adminRouteBlocked = isAdminRoute\s*&& !isOpenTestPagesRuntime/);
  assert.match(source, /const adminRouteBlocked = isAdminRoute\s*&& adminGuardCanDecide/);
  assert.match(source, /const adminRouteChecking = isAdminRoute\s*&& !isAdmin/);
  assert.match(source, /authSession\.status === "authenticated"/);
  assert.match(source, /AdminRouteGuardState/);
});
