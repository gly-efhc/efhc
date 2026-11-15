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
  assert.match(source, /!walletModalOpenRef\.current &&\s*Date\.now\(\) - lastInteractionAt >= 6000/);
  assert.doesNotMatch(source, /staleDetectedAt|lastInteractionAt < 6000 &&/);
});
