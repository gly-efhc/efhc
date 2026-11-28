import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (p) => readFileSync(new URL(p, sourceUrl), "utf8");
// Rebased in v888: the v877 expectation that Pages disables Back was the
// regression itself. Preserve this test filename for test-history continuity.
test("Pages and Android share the same navigation guard on every route", () => {
  const src = read("../lib/appBackNavigation.ts");
  assert.match(src, /router\.events\.on\("routeChangeComplete", onRouteChange\)/);
  assert.match(src, /window\.addEventListener\("popstate", onPopState, true\)/);
  assert.match(src, /document\.addEventListener\("backbutton", onNativeBack\)/);
  assert.match(src, /bridgeWindow\.__EFHC_ANDROID_BACK__ = bridgeHandler/);
  assert.match(src, /window\.history\.pushState\(/);
  assert.doesNotMatch(src, /if \(process\.env\.NEXT_PUBLIC_EFHC_PAGES_PREVIEW === "1"\) \{\s*return \(\) =>/);
  assert.doesNotMatch(src, /efhc-app-back-guard/);
});
test("Modal portal stands above onboarding and can be scrolled entirely within viewport", () => {
  const css = read("../../public/react-runtime-layout.css");
  // Check the stylesheet actually loaded by the current application, not the retired import.
  assert.match(css, /\.efhc-modal-overlay\[data-modal-portal="body"\]\[data-modal-surface="confirmation"\]\s*\{/);
  assert.match(css, /z-index:\s*2147483100\s*!important/);
  assert.match(css, /height:\s*100dvh\s*!important/);
  assert.match(css, /max-height:\s*calc\(100dvh - 32px\)/);
  assert.match(css, /overflow-y:\s*auto/);
  const globals = read("../styles/globals.css");
  assert.match(globals, /z-index:\s*2147483000/);
  const app = read("../pages/_app.tsx");
  assert.match(app, /!isBrowserShop \? <>[\s\S]*?\/react-runtime-layout\.css`/);
  assert.match(css, /\.efhc-modal-body\s*\{[^}]*overflow-y:\s*auto/s);
  assert.ok(app.indexOf('/react-runtime-layout.css') > app.indexOf('/user-shell.css'));
});
test("Modal header supports pointer dragging, viewport clamp and keeps close action", () => {
  const src = read("../components/ui/Modal.tsx");
  for (const value of ['onPointerDown={onDragStart}', 'onPointerMove={onDragMove}',
    'onPointerUp={onDragEnd}', 'data-modal-drag-handle="true"',
    'window.innerWidth - rect.right', 'window.innerHeight - rect.bottom',
    'onClick={props.onClose}', 'if (!props.closeDisabled) props.onClose()',
  ]) assert.ok(src.includes(value), value);
});
