import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import path from "node:path";

const root=path.resolve(import.meta.dirname,"../../..");
const read=p=>readFileSync(path.join(root,p),"utf8");

test("Serwist source candidate has no independent PWA cache writer",()=>{
 const sw=read("ci/pages-tools/sw-serwist.js");
 const build=read("ci/pages-tools/inject_serwist.mjs");
 const cfg=read("frontend/serwist.config.mjs");
 assert.match(sw,/from "serwist"/);
 assert.match(sw,/new Serwist\(/);
 assert.match(sw,/self\.__SW_MANIFEST/);
 assert.match(sw,/Promise\.all\(\[run\(\),run\(\)\]\)/);
 assert.doesNotMatch(sw,/\bcache\.put\s*\(/);
 assert.match(sw,/async function retireLegacyCachesOnce\(/);
 assert.doesNotMatch(sw,/from ["']workbox-/);
 assert.match(build,/EFHC_SERWIST_CONFIGURATOR_PASS/);
 assert.match(cfg,/from "@serwist\/next\/config"/);
 assert.match(cfg,/precachePrerendered:false/);
 assert.match(cfg,/globPatterns:\[\]/);
});


test("Serwist defers activation and document reload while the TON Connect modal is open", () => {
  const source = read("frontend/src/components/PwaRuntimeStatus.tsx");
  assert.match(source, /import \{ useWalletProvider \} from "\.\.\/lib\/wallet-provider";/);
  assert.match(source, /walletModalOpenRef\.current \|\|\s*Date\.now\(\) - lastInteractionAt < 6000/);
  assert.match(source, /!walletModalOpenRef\.current && !walletHandoffPending &&\s*Date\.now\(\) - lastInteractionAt >= 6000/);
  assert.doesNotMatch(source, /staleDetectedAt|lastInteractionAt < 6000 &&/);
});


test("legacy Serwist control messages cannot bypass EFHC safety or public-only prefetch", () => {
 const sw=read("ci/pages-tools/sw-serwist.js");
 const runtime=read("frontend/src/components/PwaRuntimeStatus.tsx");
 const doc=read("frontend/src/pages/_document.tsx");
 // Serwist's own SKIP_WAITING and CACHE_URLS listeners must never receive
 // the legacy messages before EFHC applies scope and operation guards.
 const interception=sw.indexOf('self.addEventListener("message", event => {');
 const native=sw.indexOf("const sw = new Serwist(");
 assert.ok(interception>=0 && interception<native,
   "legacy protocol interception must be registered before the native SDK");
 const early=sw.slice(interception,native);
 assert.match(early,/event\.stopImmediatePropagation\(\)/);
 assert.match(early,/data\.type === "SKIP_WAITING"/);
 assert.match(early,/data\.type === "CACHE_URLS"/);
 assert.match(sw,/data\.efhcSafeToActivate !== true/);
 assert.match(sw,/activationReadyClients\.set\(senderId, Date\.now\(\)\)/);
 assert.match(sw,/windows\.some\(client => now - \(activationReadyClients\.get\(client\.id\) \|\| 0\) > 4500\)/);
 assert.match(sw,/data\.type==="CLIENT_ACTIVATION_BUSY"/);
 assert.match(runtime,/type: "CLIENT_ACTIVATION_BUSY"/);
 assert.match(sw,/event\.source\?\.url/);
 assert.match(sw,/data\.type==="ACTIVATE_WHEN_SAFE"/);
 assert.match(sw,/data\.type==="PREFETCH_PRIORITY"/);
 assert.match(runtime,/type: "ACTIVATE_WHEN_SAFE"/);
 assert.match(runtime,/type: "PREFETCH_PRIORITY"/);
 assert.match(doc,/ACTIVATE_WHEN_SAFE/);
 assert.doesNotMatch(runtime,/type: "SKIP_WAITING"|type: "CACHE_URLS"/);
 assert.doesNotMatch(doc,/SKIP_WAITING/);
});

test("PWA maintenance is Serwist-scoped and never erases personal identity", () => {
 const sw=read("ci/pages-tools/sw-serwist.js");
 const settings=read("frontend/src/components/profile/ProfileSettingsDialog.tsx");
 assert.match(sw,/data\.type==="CLEAN_STALE_PUBLIC_CACHE"/);
 assert.match(sw,/NO_SERWIST_NATIVE_EQUIVALENT/);
 assert.match(sw,/for \(const name of \[cacheNames\.pages, cacheNames\.assets\]\)/);
 assert.match(sw,/clients\.length !== 1/);
 assert.match(sw,/event\.data\.documentBuildId !== CONFIG\.build_id/);
 assert.match(sw,/published\.build_id !== CONFIG\.build_id/);
 assert.match(sw,/status:failed \? "partial" : "complete"/);
 assert.doesNotMatch(sw,/localStorage\.clear|sessionStorage\.clear|indexedDB\.deleteDatabase/);
 assert.match(settings,/new MessageChannel\(\)/);
 assert.match(settings,/CLEAN_STALE_PUBLIC_CACHE/);
 assert.match(settings,/PUBLIC_CACHE_CLEAN_RESULT/);
 assert.match(settings,/role="status"/);
 assert.doesNotMatch(settings,/caches\.delete\(|caches\.keys\(|localStorage\.clear\(/);
});
