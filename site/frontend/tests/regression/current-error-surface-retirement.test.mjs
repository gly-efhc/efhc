import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {sourceRuntime} from "../helpers/source-runtime.mjs";

test("A failed Withdraw render keeps canonical page sections without fatal error windows",()=>{
  const runtime=sourceRuntime();
  const Surface=runtime.load("components/QuietPageSurface.tsx").QuietPageSurface;
  const t=key=>key==="withdraw.title"?"Вывод":key;
  const html=renderToStaticMarkup(React.createElement(Surface,{
    pathname:"/efhc/withdraw/",t,
  }));
  assert.match(html,/data-recovery-route="withdraw"/);
  assert.match(html,/class="efhc-game-page/);
  assert.match(html,/efhc-withdraw-hero/);
  assert.match(html,/withdraw.new_request/);
  assert.match(html,/withdraw.latest_operations/);
  assert.match(html,/— EFHCm/);
  assert.match(html,/<input[^>]*disabled/);
  assert.match(html,/<button[^>]*disabled/);
  assert.doesNotMatch(html,/efhc-safe-error-state|data-app-render-error|data-safe-error-status/);
  assert.doesNotMatch(html,/500|service.temporarily|application.error/i);
});

test("A failed nonfinancial render preserves the route shell instead of a 500 dialog",()=>{
  const Surface=sourceRuntime().load("components/QuietPageSurface.tsx").QuietPageSurface;
  const html=renderToStaticMarkup(React.createElement(Surface,{
    pathname:"/efhc/referrals/",t:key=>key,
  }));
  assert.match(html,/data-recovery-route="referrals"/);
  assert.match(html,/class="efhc-game-hero/);
  assert.match(html,/class="efhc-game-section/);
  assert.doesNotMatch(html,/efhc-safe-error-state|data-app-render-error/);
});

test("The React ErrorBoundary and fallback route never mount a full-screen 500 card",()=>{
  const boundary=readFileSync(new URL("../../src/components/ErrorBoundary.tsx",import.meta.url),"utf8");
  const server=readFileSync(new URL("../../src/pages/500.tsx",import.meta.url),"utf8");
  assert.match(boundary,/QuietPageSurface/);
  assert.match(server,/QuietPageSurface/);
  assert.doesNotMatch(boundary,/SafeErrorState|status=\{500\}/);
  assert.doesNotMatch(server,/SafeErrorState|status=\{status\}/);
});

test("Retired pages and fatal error cards are physically absent",()=>{
  for(const relative of ["../../src/pages/dev","../../public/dev",
    "../../src/components/ui/SafeErrorState.tsx"]) {
    assert.equal(existsSync(new URL(relative,import.meta.url)),false,
      "A deleted public screen must not reappear: "+relative);
  }
});
