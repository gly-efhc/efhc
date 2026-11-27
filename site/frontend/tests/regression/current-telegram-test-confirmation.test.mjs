import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = (path) => readFileSync(new URL(`../../src/${path}`, import.meta.url), "utf8");
function telegramConfirm(WebApp, browserConfirm = () => undefined) {
  const code = source("lib/telegram.ts");
  const slice = (start, end) => code.slice(code.indexOf(start), code.indexOf(end));
  return runInNewContext(stripTypeScriptTypes((
    slice("export function getTelegramWebApp(", "export function isTelegramMiniApp(") +
    slice("export async function telegramConfirm(", "export function telegramAlert(")
  ).replace(/^export /gm, "")) + "\ntelegramConfirm", {
    window: { Telegram: { WebApp }, confirm: browserConfirm }, setTimeout, clearTimeout,
  });
}

test("TEST Telegram waits for explicit OK delivered by the SDK callback", async () => {
  let callback;
  let settled = false;
  const confirm = telegramConfirm({
    initData: "synthetic",
    showConfirm(_msg, cb) { callback = cb; },
  });
  const result = confirm("Confirm", "Detail", true).then((value) => { settled = true; return value; });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  callback(true);
  callback(false);
  assert.equal(await result, true);
});

test("TEST Telegram denies cancellation, malformed decisions and a failed native popup", async () => {
  for (const choice of [false, undefined, "true"]) {
    const confirm = telegramConfirm({ initData: "synthetic", showConfirm(_msg, cb) { cb(choice); } });
    assert.equal(await confirm("Confirm", undefined, true), false);
  }
  const confirm = telegramConfirm({
    initData: "synthetic",
    showConfirm() { throw new Error("Popup already open"); },
  }, () => true);
  assert.equal(await confirm("Confirm", undefined, true), false);
});

test("ordinary browser confirmation is unchanged", async () => {
  const confirm = telegramConfirm(undefined, (message) => message === "Confirm");
  assert.equal(await confirm("Confirm", undefined, true), true);
  assert.equal(await confirm("Cancel", undefined, true), false);
});

test("confirmed operation is single-flight and never dispatches after cancellation or context change", async () => {
  const code = source("lib/confirmed-operation.ts");
  const run = runInNewContext(stripTypeScriptTypes(code.replace(/^export /gm, "")) + "\nrunConfirmedOperation");
  for (const scenario of ["approve", "cancel", "account", "relogin", "route", "amount", "wallet", "target", "ad", "send"]) {
    let resolveChoice;
    let resolveAd;
    let pendingSend;
    const context = { owner: "A", session: 1, route: "/withdraw", amount: "10.00000000", wallet: "wallet-A", target: "request-A" };
    const before = JSON.stringify(context);
    const valid = () => JSON.stringify(context) === before;
    let calls = 0;
    const invoke = () => run(
      valid,
      () => new Promise((resolve) => { resolveChoice = resolve; }),
      async (beforeSend) => {
        if (scenario === "ad") await new Promise((resolve) => { resolveAd = resolve; });
        if (scenario === "send") await new Promise((resolve) => { pendingSend = resolve; });
        if (beforeSend()) calls++;
      },
    );
    const task = invoke();
    let secondInvoked = false;
    await run(valid, async () => { secondInvoked = true; return true; }, async () => { calls++; });
    assert.equal(secondInvoked, false);
    assert.equal(calls, 0);
    const keys = {account:"owner",relogin:"session",route:"route",amount:"amount",wallet:"wallet",target:"target"};
    if (keys[scenario]) context[keys[scenario]] = "changed";
    resolveChoice(scenario !== "cancel");
    if (scenario === "ad" || scenario === "send") {
      await new Promise((resolve) => setImmediate(resolve));
      context.session++;
      (resolveAd || pendingSend)();
    }
    await task;
    assert.equal(calls, scenario === "approve" ? 1 : 0, scenario);
  }
});

test("TEST transport checks the same confirmation again after asynchronous CSRF", async () => {
  const code = source("demo/transport.ts");
  const transport = stripTypeScriptTypes(code
    .slice(code.indexOf("export async function demoRawRequest("), code.indexOf("export const demoBackendTransport"))
    .replace(/^export /gm, ""));
  for (const path of ["/api/panels/activate", "/api/exchange/convert", "/api/withdraw/request", "/api/withdraw/123/cancel"]) {
    for (const replaceSession of [false, true]) {
      let releaseCsrf;
      let auth = "Bearer synthetic-original";
      const sent = [];
      const request = runInNewContext(transport + "\ndemoRawRequest", {
        normalizeApiPath: (value) => value,
        currentDemoSessionScope: () => "operator",
        getAuthAuthorizationHeader: () => auth,
        sessionCsrf: () => new Promise((resolve) => { releaseCsrf = resolve; }),
        demoApiOrigin: () => "https://fixture.invalid",
        demoFetch: async (url, opts) => { sent.push({ url, opts }); return { status: 200 }; },
        ApiError: class extends Error { constructor({ code }) { super(code); } },
      });
      const originalAuth = auth;
      const pending = request(path, "POST", {
        idempotencyKey: "original-test-key",
        beforeSend: () => auth === originalAuth,
      });
      if (replaceSession) auth = "Bearer synthetic-different-session";
      releaseCsrf("synthetic-csrf");
      if (replaceSession) {
        await assert.rejects(pending, /CONFIRMED_OPERATION_CONTEXT_CHANGED/);
        assert.equal(sent.length, 0);
      } else {
        await pending;
        assert.equal(sent.length, 1);
        assert.equal(sent[0].url, "https://fixture.invalid" + path);
        assert.equal(sent[0].opts.headers.Authorization, originalAuth);
        assert.equal(sent[0].opts.headers["Idempotency-Key"], "original-test-key");
      }
    }
  }
});

test("EFHC TEST coordinator rejects a replaced session even when the account is unchanged", async () => {
  const code = source("hooks/useTestTelegramConfirmation.ts");
  const hookCode = stripTypeScriptTypes(code.slice(code.indexOf("export function")).replace(/^export /gm, ""));
  const operation = stripTypeScriptTypes(source("lib/confirmed-operation.ts").replace(/^export /gm, ""));
  let account = "0000000001";
  let authRevision = 1;
  let onNavigation;
  let pending;
  let sends = 0;
  const hook = runInNewContext(operation + "\n" + hookCode + "\nuseTestTelegramConfirmation", {
    Router: { events: { on(_event, callback) { onNavigation = callback; }, off() {} } },
    useEffect: (effect) => { effect(); },
    useRef: (current) => ({ current }),
    useAuthSessionController: () => ({ status: "authenticated", context: { global_id: account } }),
    isDemoBackendMode: () => true,
    isTelegramConfirmationTest: () => true,
    getAuthAuthorizationHeader: () => "Bearer synthetic-credential",
    getAuthSessionRevision: () => authRevision,
    window: { location: { href: "https://fixture.invalid/efhc/withdraw/" } },
  });
  for (const scenario of ["session", "navigation", "approval"]) {
    const run = hook(account, { amount: "10.00000000" });
    const operationDone = run(
      () => new Promise((resolve) => { pending = resolve; }),
      (current) => current.amount === "10.00000000",
      async (beforeSend) => { if (beforeSend()) sends++; },
    );
    if (scenario === "session") authRevision++;
    if (scenario === "navigation") onNavigation();
    pending(true);
    await operationDone;
    assert.equal(sends, scenario === "approval" ? 1 : 0);
  }
});

test("panel confirmation uses EFHC Modal after settings gates and retains cancellation and session guard", () => {
  const layout = source("components/Layout.tsx");
  const panels = source("pages/panels.tsx");
  const hook = source("hooks/useTestTelegramConfirmation.ts");
  for (const marker of ['if (!props.settings.confirm_actions) return true;', 'if (!gate) return true;', 'kind === "purchase" && router.pathname === "/panels"', 'return await confirmPanelPurchase(title, detail)', 'surface="panel-confirmation"', 'portalColorThemeId={customization.colorThemeId}', 'onClose={() => settlePanelConfirmation(false)}', 'onClick={() => settlePanelConfirmation(true)}', 'subscribeAuthSessionInvalidation(cancel)', 'router.events.on("routeChangeStart", cancel)', 'pendingPanelConfirmation.current = null']) assert.ok(layout.includes(marker), marker);
  assert.ok(panels.includes('!customization.mutationBlocked && (canActivatePanel || Boolean(pendingPurchaseKey)),\n    true,'));
  assert.ok(hook.includes('!guardAsyncConfirmation && !isTelegramConfirmationTest(isDemoBackendMode())'));
});
