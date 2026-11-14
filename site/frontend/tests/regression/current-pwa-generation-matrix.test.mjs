/** Serwist-only PWA generation regression contracts.
 * Source invariants are paired with the mandatory real Chromium A→B→C,
 * interrupted-loading, old-tab and offline route acceptance.
 * The former custom Service Worker test harness was retired with that engine.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,mkdtempSync,rmSync,existsSync} from "node:fs";
import {tmpdir} from "node:os";
import {createHash} from "node:crypto";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {spawnSync} from "node:child_process";

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const toolsDir=path.resolve(frontend,"../ci/pages-tools");
const read=p=>readFileSync(path.join(frontend,p),"utf8");
const worker=readFileSync(path.join(toolsDir,"sw-serwist.js"),"utf8");
const builder=readFileSync(path.join(toolsDir,"inject_serwist.mjs"),"utf8");
const cfg=read("serwist.config.mjs");
const runtime=read("src/components/PwaRuntimeStatus.tsx");

test("T1: release-specific CSS fingerprints are included before Serwist generates one worker",t=>{
  const folder=mkdtempSync(path.join(tmpdir(),"efhc-serwist-css-"));
  t.after(()=>rmSync(folder,{recursive:true,force:true}));
  function write(file,value) {
    const target=path.join(folder,file);
    mkdirSync(path.dirname(target),{recursive:true});
    writeFileSync(target,value,"utf8");
  }
  write("index.html",'<html><head><link rel="stylesheet" href="/efhc/visual.css"></head><body><script id="__NEXT_DATA__"></script><script src="/efhc/_next/static/main.js"></script></body></html>');
  write("404.html","retired");
  write("500.html","retired");
  write("404/index.html","retired nested");
  write("500/index.html","retired nested");
  write("_next/static/main.js",'const css="/user-shell.css";');
  write("_next/static/main.css","body{color:white}");
  write("visual.css","body{color:red}");
  write("user-shell.css","body{margin:0}");
  write("public-runtime-config.js","window.__EFHC_PUBLIC_CONFIG__={};");
  for(const name of ["manifest.webmanifest","offline.html","offline-readonly.html"])
    copyFileSync(path.join(frontend,"public",name),path.join(folder,name));
  const invoke=tool=>spawnSync("python3",[
    path.join(toolsDir,tool),"--directory",folder,"--base-path","/efhc",
  ],{encoding:"utf8",env:process.env});
  const generated=invoke("fix_pages_assets.py");
  assert.equal(generated.status,0,generated.stderr+"\n"+generated.stdout);
  assert.equal(existsSync(path.join(folder,"404.html")),false);
  assert.equal(existsSync(path.join(folder,"500.html")),false);
  assert.equal(existsSync(path.join(folder,"404")),false);
  assert.equal(existsSync(path.join(folder,"500")),false);
  assert.equal(invoke("verify_export.py").status,0,"Serwist export and Pages assets must verify");
  const hash=name=>name.slice(0,-4)+"."+
    createHash("sha256").update(readFileSync(path.join(folder,name)))
      .digest("hex").slice(0,16)+".css";
  const cssA=hash("visual.css"),cssB=hash("user-shell.css");
  assert.ok(readFileSync(path.join(folder,"index.html"),"utf8").includes("/"+cssA));
  assert.ok(readFileSync(path.join(folder,"_next/static/main.js"),"utf8").includes("/"+cssB));
  const meta=JSON.parse(readFileSync(path.join(folder,"pwa-build.json"),"utf8"));
  assert.ok(meta.precache.includes("/efhc/"+cssA));
  assert.ok(meta.precache.includes("/efhc/"+cssB));
  assert.ok(meta.precache_critical.includes("/efhc/index.html"));
  assert.ok(meta.precache_critical.includes("/efhc/_next/static/main.js"));
  assert.ok(!meta.cache_limits,"Serwist owns native cache limits, not EFHC's old cache-policy engine");
  const first=readFileSync(path.join(folder,"pwa-build.json"),"utf8");
  assert.equal(invoke("fix_pages_assets.py").status,0,"Export must be reproducible");
  assert.equal(readFileSync(path.join(folder,"pwa-build.json"),"utf8"),first);
  const bundled=readFileSync(path.join(folder,"sw.js"),"utf8");
  assert.ok(bundled.includes("EFHC_HTML_GENERATION_MISMATCH"));
  assert.ok(!bundled.includes("self.__SW_MANIFEST"),"Configurator must inject the manifest");
});

test("T2: immutable old JS/CSS has an address-scoped legacy fallback on failed fetch",()=>{
  assert.match(worker,/async function legacyAssetFallback/);
  assert.match(worker,/legacyAssetFallback\(request\)/);
  assert.match(worker,/!result\?\.ok/,"HTTP 404 must be caught as well as exceptions");
  assert.match(worker,/\/_next/);
  assert.match(worker,/\.css/);
});

test("T3: unrelated applications are excluded from legacy retirement",()=>{
  assert.match(worker,/const inScope/);
  assert.match(worker,/request\.url/);
  assert.match(worker,/entries\.every\(request =>/);
  assert.match(worker,/inScope\(new URL\(request\.url\)\)/);
  assert.doesNotMatch(worker,/caches\.delete\(["']?[^"']*other/);
});

test("T4: migration readiness is scoped to a verified active client",()=>{
  assert.match(worker,/data\.type==="CLIENT_BUILD_READY"/);
  assert.match(worker,/data\.buildId!==CONFIG\.build_id/);
  assert.match(worker,/expected\.has\(url\)/);
  assert.match(worker,/readyClients\.add\(event\.source\.id\)/);
});

test("T5: closing old tabs can release only proved legacy EFHC buckets",()=>{
  assert.match(worker,/retireLegacyCachesOnce\(\)/);
  assert.match(worker,/windows\.some\(client => !readyClients\.has\(client\.id\)\)/);
  assert.match(worker,/for \(const name of await legacyPublicCaches\(\)\) await caches\.delete\(name\)/);
});

test("T6: an unready old tab protects its cache",()=>{
  assert.match(worker,/if \(!windows\.length \|\| windows\.some/);
  assert.match(worker,/readyClients/);
  assert.match(worker,/if \(data\.buildId!==CONFIG\.build_id/);
});

test("T7: A→B→C worker revisions use native Serwist precache lifecycle",()=>{
  assert.match(worker,/precacheEntries:self\.__SW_MANIFEST/);
  assert.match(worker,/cleanupOutdatedCaches:true/);
  assert.match(worker,/new Serwist\(/);
  assert.doesNotMatch(worker,/new Workbox|from ["']workbox-/);
});

test("T8: a missing critical resource rejects atomic installation, without committing a partial custom cache",()=>{
  assert.match(builder,/config\.precache_critical/);
  assert.match(builder,/readFile\(path\.join\(root,url\.slice/);
  assert.match(worker,/precacheOptions:\{/);
  assert.doesNotMatch(worker,/\bcache\.put\s*\(/);
  assert.match(cfg,/additionalPrecacheEntries:critical/);
});

test("T9: build metadata and private APIs are network only",()=>{
  assert.match(worker,/const networkOnly = new NetworkOnly/);
  assert.match(worker,/isSensitive\(url\.pathname\),handler:networkOnly/);
  assert.match(worker,/scoped\("pwa-build\.json"\),handler:networkOnly/);
  assert.doesNotMatch(worker,/BackgroundSyncPlugin|Queue\(/);
});

test("T10: no stale-generation HTML fallback can mix releases",()=>{
  assert.match(worker,/EFHC_HTML_GENERATION_MISMATCH/);
  assert.match(worker,/cachedResponseWillBeUsed/);
  assert.match(worker,/if \(!expected\.has\(pathname\)\)/);
  assert.doesNotMatch(worker,/legacyHtmlFallback|efhc-legacy-html/);
});

test("T11: Serwist alone handles public runtime cache writes and expiry",()=>{
  assert.match(worker,/new CacheFirst/);
  assert.match(worker,/new NetworkFirst/);
  assert.match(worker,/new StaleWhileRevalidate/);
  assert.match(worker,/new ExpirationPlugin/);
  assert.doesNotMatch(worker,/\bcache\.put\s*\(/);
  assert.doesNotMatch(runtime,/SET_CACHE_POLICY/);
  assert.doesNotMatch(runtime,/resolveAdaptiveCachePolicy/);
});

test("T12: idle reload remains bounded and protects active financial operations",()=>{
  assert.match(runtime,/attempts >= 3/);
  assert.match(runtime,/lastAttemptAt/);
  assert.match(runtime,/retryDelayMs/);
  assert.match(runtime,/efhc:pwa-upgrade-stalled/);
  assert.match(runtime,/sessionStorage\.removeItem\(verifiedKey\)/);
  assert.match(runtime,/queryClient\.isMutating\(\) > 0/);
  assert.match(runtime,/efhcSafeToActivate: true/);
});

test("Offline deferred resources are parallel but cached only by native Serwist",()=>{
  assert.match(worker,/Promise\.all\(\[run\(\),run\(\)\]\)/);
  assert.match(worker,/strategy\.handle\(\{event,request\}\)/);
  assert.doesNotMatch(worker,/\bcache\.put\s*\(/);
  assert.match(runtime,/connectionAllowsPrefetch/);
});

test("A single scoped Service Worker is emitted by Serwist Configurator",()=>{
  assert.match(cfg,/from "@serwist\/next\/config"/);
  assert.match(cfg,/precachePrerendered:false/);
  assert.match(cfg,/globPatterns:\[\]/);
  assert.match(builder,/EFHC_SERWIST_CONFIGURATOR_PASS/);
  assert.doesNotMatch(builder,/inject_workbox|sw-workbox/);
  assert.match(runtime,/serviceWorker\.register/);
});

test("Background music stops on pagehide/freeze and cannot resume while hidden",()=>{
  const audio=read("src/components/BackgroundMusicController.tsx");
  assert.match(audio,/addEventListener\("pagehide", stopForHiddenPage\)/);
  assert.match(audio,/addEventListener\("visibilitychange", onVisibilityChange\)/);
  assert.match(audio,/addEventListener\("freeze", stopForHiddenPage\)/);
  assert.match(audio,/gain\.gain\.value = 0/);
  assert.match(audio,/source\.stop\(\)/);
  assert.match(audio,/context\.suspend\(\)/);
  assert.match(audio,/if \(!active \|\| !visible \|\| !buffer/);
  assert.match(audio,/if \(!enabled \|\| typeof window === "undefined"\) return/);
  assert.match(audio,/removeEventListener\("pagehide", stopForHiddenPage\)/);
});
