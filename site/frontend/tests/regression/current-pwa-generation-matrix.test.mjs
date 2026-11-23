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
import {runInNewContext} from "node:vm";

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
  assert.ok(meta.precache_critical.includes("/efhc/"+cssA));
  assert.ok(meta.precache_critical.includes("/efhc/"+cssB));
  assert.deepEqual(meta.precache.filter(url => /\.(?:html|js|css)$/.test(url)
    && !meta.precache_critical.includes(url)), [],
    "All code and HTML must be installed before old release URLs disappear");
  assert.ok(!meta.cache_limits,"Serwist owns native cache limits, not EFHC's old cache-policy engine");
  const first=readFileSync(path.join(folder,"pwa-build.json"),"utf8");
  assert.equal(invoke("fix_pages_assets.py").status,0,"Export must be reproducible");
  assert.equal(readFileSync(path.join(folder,"pwa-build.json"),"utf8"),first);
  const bundled=readFileSync(path.join(folder,"sw.js"),"utf8");
  assert.ok(bundled.includes("EFHC_HTML_GENERATION_MISMATCH"));
  assert.ok(!bundled.includes("self.__SW_MANIFEST"),"Configurator must inject the manifest");
});

test("T2: immutable CSS/JS stay version-addressed and Serwist handles asset caching",()=>{
  assert.match(worker,/_next/); assert.match(worker,/static/);
  assert.match(worker,/new CacheFirst\(/);
  assert.match(worker,/publicAssets/);
  assert.doesNotMatch(worker,/legacyAssetFallback|legacyPublicCaches/);
});

test("T3: unrelated applications are untouched by Serwist scope",()=>{
  assert.match(worker,/const inScope/);
  assert.match(worker,/url\.origin === self\.location\.origin/);
  assert.match(worker,/url\.pathname\.startsWith\(BASE \+ "\/"\)/);
  assert.match(worker,/publicRuntimeCaches/);
  assert.match(worker,/caches\.delete\(name\)/);
});

test("T4: no EFHC custom client-generation cache handshake remains",()=>{
  assert.match(worker,/cleanupOutdatedCaches:true/);
  assert.doesNotMatch(worker,/CLIENT_BUILD_READY|readyClients/);
  assert.match(runtime,/serviceWorker\.register/);
});

test("T5: Serwist lifecycle supersedes EFHC manual legacy retirement",()=>{
  assert.match(worker,/sw\.addEventListeners\(\)/);
  assert.doesNotMatch(worker,/retireLegacyCachesOnce|legacyAssetFallback/);
  assert.match(worker,/caches\.delete\(name\)/);
});

test("T6: old tabs are not overridden by a custom forced activation",()=>{
  assert.match(worker,/skipWaiting:false/);
  assert.equal((worker.match(/self\.skipWaiting\(/g) || []).length, 1, "the sole explicit activation call is the guarded historic bridge");
  assert.match(runtime,/type:"SKIP_WAITING"/);
  assert.match(runtime,/EFHC_PWA_CHECK_CLIENTS/);
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

test("T12: idle reload protects active financial operations",()=>{
  assert.match(runtime,/queryClient\.isMutating\(\) === 0/);
  assert.match(runtime,/!walletModalRef\.current && !handoffPending/);
  assert.match(runtime,/!activeEditor\(\)/);
  assert.match(runtime,/refreshPending = false/);
  assert.match(runtime,/safeForUpgrade/);
  assert.doesNotMatch(runtime,/efhc:pwa-upgrade-stalled|ACTIVATE_WHEN_SAFE/);
});

test("Public background resource caching uses native Serwist CACHE_URLS only",()=>{
  assert.match(worker,/sw\.addEventListeners\(\)/);
  assert.doesNotMatch(worker,/prefetchDeferred|PREFETCH_PRIORITY/);
  assert.doesNotMatch(worker,/\bcache\.put\s*\(/);
  assert.match(runtime,/type:"CACHE_URLS",payload:\{urlsToCache\}/);
  assert.match(runtime,/precache_deferred/); assert.match(runtime,/CACHE_URLS/);
  assert.match(runtime,/manifest\.build_id !== documentBuild/);
  assert.match(runtime,/registration\?\.waiting/);
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

test("Historic Telegram document handoff is scoped, visible and single-client only", async () => {
  const build = "a".repeat(24);
  const page = {id:"old",type:"window",url:"https://example.test/efhc/web-profile/",visibilityState:"visible"};
  const source = worker.replace(/^import \{[\s\S]*?\} from "serwist";/m, "");
  const messages = [];
  let clients = [page], calls = 0, waiting = true;
  let onMessage;
  class Strategy {
    addEventListeners() {}
  }
  const self = {
    location:{origin:"https://example.test"},
    get registration() { return {waiting:waiting ? {state:"installed"} : null}; },
    clients:{matchAll:async opts=>{
      assert.equal(opts.type,"window");
      assert.equal(opts.includeUncontrolled,true);
      return clients;
    }},
    addEventListener(type, listener) { if (type==="message") onMessage=listener; },
    skipWaiting:async()=>{ calls++; },
  };
  runInNewContext(source,{self,URL,
    __EFHC_BUILD_CONFIG__:{build_id:build,precache:[]},__EFHC_BASE_PATH__:"/efhc",
    Serwist:Strategy,CacheFirst:Strategy,NetworkFirst:Strategy,NetworkOnly:Strategy,
    StaleWhileRevalidate:Strategy,ExpirationPlugin:Strategy,CacheExpiration:Strategy});
  const send=async (data, sender=page)=>{
    let settled;
    onMessage({data,source:sender,ports:[{postMessage:v=>messages.push(v)}],
      waitUntil:p=>{settled=p;}});
    await settled;
  };
  const exact={type:"ACTIVATE_WHEN_SAFE",buildId:build,efhcSafeToActivate:true};
  await send({...exact,buildId:"b".repeat(24)});
  await send({...exact,efhcSafeToActivate:false});
  await send(exact,{...page,id:"different-window"});
  await send(exact,{...page,url:"https://example.test/other/"});
  await send(exact,{...page,type:"serviceworker"});
  clients=[{...page,visibilityState:"hidden"}]; await send(exact);
  clients=[page,{...page,id:"second"}]; await send(exact);
  clients=[page,{...page,id:"hidden-second",visibilityState:"hidden"}]; await send(exact);
  clients=[page]; waiting=false; await send(exact);
  assert.equal(calls,0);
  waiting=true; await send(exact);
  assert.equal(calls,1);
  await send({type:"GET_ACTIVE_BUILD"},{...page,url:"https://example.test/other/"});
  assert.equal(messages.length,0);
  await send({type:"GET_ACTIVE_BUILD"});
  assert.equal(messages.length,1);
  assert.equal(messages[0].type,"ACTIVE_BUILD");
  assert.equal(messages[0].buildId,build);
});

test("A worker-source-only change creates a new build generation without hashing generated sw.js", t=>{
  const folder=mkdtempSync(path.join(tmpdir(),"efhc-worker-generation-"));
  t.after(()=>rmSync(folder,{recursive:true,force:true}));
  const exportDir=path.join(folder,"out");
  mkdirSync(path.join(exportDir,"_next/static"),{recursive:true});
  writeFileSync(path.join(exportDir,"index.html"),'<html><head><script src="/efhc/_next/static/test.js"></script></head></html>');
  writeFileSync(path.join(exportDir,"_next/static/test.js"),"void 0;");
  writeFileSync(path.join(exportDir,"manifest.webmanifest"),"{}");
  copyFileSync(path.join(toolsDir,"fix_pages_assets.py"),path.join(folder,"fix_pages_assets.py"));
  const workerSource=path.join(folder,"sw-serwist.js");
  writeFileSync(workerSource,"export default 1;");
  const configure=()=>{
    const script="import sys; from pathlib import Path; from fix_pages_assets import configure_pwa; configure_pwa(Path(sys.argv[1]), '/efhc')";
    const result=spawnSync("python3",["-B","-c",script,exportDir],{cwd:folder,encoding:"utf8"});
    assert.equal(result.status,0,result.stderr);
    return JSON.parse(readFileSync(path.join(exportDir,"pwa-build.json"),"utf8")).build_id;
  };
  const first=configure();
  writeFileSync(path.join(exportDir,"sw.js"),"generated output with a different hash");
  assert.equal(configure(),first);
  writeFileSync(workerSource,"export default 2;");
  const next=configure();
  assert.notEqual(next,first);
  assert.equal(configure(),next);
});
