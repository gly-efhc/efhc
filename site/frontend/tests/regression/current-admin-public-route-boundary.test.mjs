import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

function path(relative) {
  return new URL(relative, import.meta.url);
}

function source(relative) {
  return readFileSync(path(relative), "utf8");
}

test("public Pages cannot export the retired Neon TEST login and top-up console", () => {
  assert.equal(existsSync(path("../../src/pages/dev/neon.tsx")), false);
  assert.equal(existsSync(path("../../src/pages/dev/neon/index.tsx")), false);
  assert.equal(existsSync(path("../../src/pages/dev/neon/index.jsx")), false);
});

test("denied Admin UI never navigates to a retired public password entry", () => {
  const layout = source("../../src/components/Layout.tsx");
  assert.doesNotMatch(layout, /\/dev\/neon\/?/);
  assert.doesNotMatch(layout, /Ввести ключ просмотра Admin/);
  assert.match(layout, /data-admin-access="denied"/);
  assert.match(layout, /Для входа необходима действующая серверная сессия/);
});

test("real protected Admin pages remain intact and server access stays authoritative", () => {
  for (const route of ["index.tsx", "users.tsx", "bank.tsx", "efhc-deposits.tsx"]) {
    assert.equal(existsSync(path("../../src/pages/admin/" + route)), true, route);
  }
  const app = source("../../src/pages/_app.tsx");
  assert.match(app, /fetchAdminAccess\(\)/);
  assert.match(app, /const adminRouteBlocked = isAdminRoute/);
  assert.match(app, /<AdminRouteGuardState checking=\{adminRouteChecking\}/);
});
