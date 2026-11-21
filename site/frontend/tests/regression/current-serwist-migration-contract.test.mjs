import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import path from "node:path";
const root = path.resolve(import.meta.dirname,"../../..");
const read = p => readFileSync(path.join(root,p),"utf8");

test("Only Serwist owns HTTP caching, precache revisions and expiration", () => {
  const sw = read("ci/pages-tools/sw-serwist.js");
  const build = read("ci/pages-tools/inject_serwist.mjs");
  const config = read("frontend/serwist.config.mjs");
  assert.match(sw,/from "serwist"/);
  assert.match(sw,/const sw = new Serwist\(/);
  assert.match(sw,/precacheEntries:self\.__SW_MANIFEST/);
  assert.match(sw,/cleanupOutdatedCaches:true/);
  assert.match(sw,/new ExpirationPlugin\(/);
  assert.match(sw,/sw\.addEventListeners\(\)/);
  assert.match(build,/EFHC_SERWIST_CONFIGURATOR_PASS/);
  assert.match(config,/from "@serwist\/next\/config"/);
  assert.match(config,/globPatterns:\[\]/);
  assert.doesNotMatch(sw,/\bcache\.put\s*\(|\bcaches\.open\s*\(/);
  assert.match(sw,/publicRuntimeCaches/);
  assert.match(sw,/caches\.delete\(name\)/);
  assert.doesNotMatch(sw,/legacyAssetFallback|retireLegacyCachesOnce|CLIENT_BUILD_READY|GET_CACHE_STATUS/);
});

test("Native Serwist handles waiting, CACHE_URLS and client update checks", () => {
  const sw=read("ci/pages-tools/sw-serwist.js");
  const runtime=read("frontend/src/components/PwaRuntimeStatus.tsx");
  const doc=read("frontend/src/pages/_document.tsx");
  assert.match(sw,/skipWaiting:false/);
  assert.match(runtime,/serviceWorker\.register/);
  assert.match(runtime,/registration\.update\(\)/);
  assert.match(runtime,/type:"CACHE_URLS",payload:\{urlsToCache\}/);
  assert.match(runtime,/navigator\.serviceWorker\.addEventListener\("controllerchange"/);
  assert.doesNotMatch(runtime,/ACTIVATE_WHEN_SAFE|PREFETCH_PRIORITY|GET_ACTIVE_BUILD|CLIENT_BUILD_READY|CACHE_STATUS/);
  assert.match(runtime,/EFHC_PWA_CHECK_CLIENTS/);
  assert.match(runtime,/type:"SKIP_WAITING"/);
  assert.match(sw,/self\.addEventListener\("message"/);
  assert.match(sw,/allClientsIdle/);
  assert.ok(!sw.includes("self.skipWaiting("), "Serwist alone activates waiting workers");
  assert.doesNotMatch(doc,/__EFHC_PWA_GATE__|efhcBootstrapScript|ACTIVATE_WHEN_SAFE|repairOnce/);
});

test("Generation integrity and private/financial network-only boundary remain", () => {
  const sw=read("ci/pages-tools/sw-serwist.js");
  assert.match(sw,/EFHC_HTML_GENERATION_MISMATCH/);
  assert.match(sw,/cachedResponseWillBeUsed/);
  assert.match(sw,/new NetworkOnly\(\)/);
  assert.match(sw,/isSensitive\(url\.pathname\),handler:networkOnly/);
  assert.match(sw,/scoped\("pwa-build\.json"\),handler:networkOnly/);
  assert.doesNotMatch(sw,/BackgroundSyncPlugin|Queue\(/);
});

test("Active transactions, wallet modal and editing block reload only", () => {
  const runtime=read("frontend/src/components/PwaRuntimeStatus.tsx");
  assert.match(runtime,/queryClient\.isMutating\(\) === 0/);
  assert.match(runtime,/!walletModalRef\.current && !handoffPending/);
  assert.match(runtime,/!activeEditor\(\)/);
  assert.match(runtime,/Date\.now\(\) - lastActivityAt >= 6000/);
  assert.match(runtime,/if \(!refreshPending \|\| !safeToReload\(\)\) return/);
  assert.match(runtime,/safeForUpgrade/);
  assert.match(runtime,/EFHC_PWA_CLIENT_SAFE/);
  assert.match(runtime,/EFHC_PWA_CHECK_CLIENTS/);
  assert.match(runtime,/type:"SKIP_WAITING"/);
});

test("OWNER-requested manual clear reaches only Serwist public runtime storage", () => {
  const settings=read("frontend/src/components/profile/ProfileSettingsDialog.tsx");
  const worker=read("ci/pages-tools/sw-serwist.js");
  const app=read("frontend/src/pages/_app.tsx");
  assert.match(settings,/registration\.update\(\)/);
  assert.match(settings,/EFHC_PWA_CLEAR_PUBLIC_CACHE/);
  assert.match(settings,/clearOutcome/);
  assert.match(worker,/publicRuntimeCaches/);
  assert.match(worker,/allClientsIdle/);
  assert.doesNotMatch(settings,/caches\.delete\(|localStorage\.clear\(|indexedDB\.deleteDatabase/);
  assert.doesNotMatch(worker,/localStorage|indexedDB|cache\.put\(/);
  assert.doesNotMatch(app,/pwaGateReady|efhc:pwa-gate-ready/);
});
