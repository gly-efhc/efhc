import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync, unlinkSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import vm from "node:vm";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const pagesTools = path.resolve(frontend, "../ci/pages-tools");
const publicDir = path.join(frontend, "public");
const read = (name) => readFileSync(path.join(frontend, name), "utf8");
const run = (script, root) => spawnSync("python3", [
  path.join(pagesTools, script), "--directory", root, "--base-path", "/efhc",
], { encoding: "utf8" });

test("Pages has a scoped Service Worker and does not delete the PWA files", () => {
  const prepare = readFileSync(path.join(pagesTools, "prepare_pages.py"), "utf8");
  const runtime = read("src/components/PwaRuntimeStatus.tsx");
  const app = read("src/pages/_app.tsx");
  assert.doesNotMatch(prepare, /public\/sw\.js'\)\.unlink/);
  assert.doesNotMatch(prepare, /public\/manifest\.webmanifest'\)\.unlink/);
  assert.match(runtime, /serviceWorker\.register\(`\$\{appBasePath\(\)\}\/sw\.js`/);
  assert.match(runtime, /efhc:pwa-registration-failed/);
  assert.match(app, /router\.basePath\}\/manifest\.webmanifest/);
  assert.doesNotMatch(runtime, /return idle\(\(\) => waiting\.postMessage\(\{ type: "SKIP_WAITING" \}/);
  assert.match(runtime, /trackedRegistration\.update\(\)/);
  assert.match(runtime, /staged\.postMessage\(\{ type: "SKIP_WAITING" \}\)/);
  assert.match(runtime, /CLIENT_BUILD_READY/);
  assert.match(runtime, /GET_ACTIVE_BUILD/);
  assert.match(read("public/sw.js"), /ACTIVE_BUILD/);
  assert.match(runtime, /controllerchange/);
  assert.match(runtime, /attemptIdleReload/);
  assert.match(runtime, /waitingActivationTimer/);
  assert.match(runtime, /activateStagedWorker\(trackedRegistration\)/);
  assert.match(runtime, /document\.addEventListener\("visibilitychange", onPageResumed\)/);
  assert.match(runtime, /const onPageResumed = \(\) => \{checkForUpdate\(\); void verifyLoadedBuild\(\);\}/);
});

test("The Pages deploy workflow requires full offline Chromium acceptance before deployment", () => {
  const releaseWorkflow = readFileSync(path.resolve(frontend, "../../.github/workflows/efhc-pages.yml"), "utf8");
  const gate = releaseWorkflow.indexOf("      - name: Require complete offline PWA and persistent React pages before publishing");
  const publish = releaseWorkflow.indexOf("      - name: Deploy real React to GitHub Pages");
  assert.ok(gate > 0, "Full offline PWA gate must be mandatory in Pages workflow");
  assert.ok(publish > gate, "PWA gate must execute before actual Pages publication");
  const gateBody = releaseWorkflow.slice(gate, releaseWorkflow.indexOf("      - name: Retain mandatory persistence evidence", gate));
  assert.match(gateBody, /EFHC_PWA_EXPORT_DIR:/);
  assert.ok(gateBody.includes("node site/frontend/tests/parity/pwa-cache-integration.mjs"));
  assert.ok(gateBody.includes("node site/frontend/tests/parity/persistent-pages.mjs"));
  assert.ok(!gateBody.includes("continue-on-error: true"));
  assert.ok(!gateBody.includes("if: ${{ inputs.full_review"));
});

test("Complete compiled export is precached, stable on repeated builds and verified fail-closed", (t) => {
  const root = mkdtempSync(path.join(tmpdir(), "efhc-full-pwa-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const put = (name, contents) => {
    const destination = path.join(root, name);
    mkdirSync(path.dirname(destination), { recursive: true });
    writeFileSync(destination, contents, "utf8");
  };
  put("index.html", '<html><script id="__NEXT_DATA__"></script><script src="/efhc/_next/static/main.js"></script></html>');
  put("panels/index.html", "<html>panels shell</html>");
  put("admin/users/index.html", "<html>admin shell without user data</html>");
  put("browser-shop/index.html", "<html>shop shell</html>");
  put("_next/static/main.js", "globalThis.__EFHC_TEST_SHELL__=true;");
  put("_next/static/main.css", "body { color: white; }");
  put("public-runtime-config.js", "window.__EFHC_PUBLIC_CONFIG__={};");
  copyFileSync(path.join(publicDir, "sw.js"), path.join(root, "sw.js"));
  copyFileSync(path.join(publicDir, "manifest.webmanifest"), path.join(root, "manifest.webmanifest"));
  copyFileSync(path.join(publicDir, "offline.html"), path.join(root, "offline.html"));
  copyFileSync(path.join(publicDir, "offline-readonly.html"), path.join(root, "offline-readonly.html"));
  const first = run("fix_pages_assets.py", root);
  assert.equal(first.status, 0, first.stderr);
  const config = JSON.parse(readFileSync(path.join(root, "pwa-build.json"), "utf8"));
  assert.equal(config.static_export, true);
  assert.ok(config.precache_critical.includes("/efhc/index.html"));
  assert.ok(config.precache_critical.includes("/efhc/_next/static/main.js"));
  assert.ok(config.precache_deferred.includes("/efhc/panels/index.html"));
  assert.ok(config.precache_deferred.includes("/efhc/admin/users/index.html"));
  const critical = new Set(config.precache_critical);
  const deferred = new Set(config.precache_deferred);
  assert.equal(critical.size + deferred.size, config.precache.length);
  assert.deepEqual([...critical, ...deferred].sort(), [...config.precache].sort());
  assert.ok([...critical].every(value => !deferred.has(value)));
  assert.match(readFileSync(path.join(root,"index.html"),"utf8"), new RegExp(`efhc-build-id" content="${config.build_id}"`));
  for (const route of ["index.html", "panels/index.html", "admin/users/index.html", "browser-shop/index.html"]) {
    assert.ok(config.precache.includes("/efhc/" + route), "Missing cached page: " + route);
  }
  assert.ok(config.precache.includes("/efhc/_next/static/main.js"));
  assert.ok(config.precache.includes("/efhc/_next/static/main.css"));
  assert.ok(!config.precache.some((url) => url.includes("/api/") || url.includes(".env")));
  const manifest = JSON.parse(readFileSync(path.join(root, "manifest.webmanifest"), "utf8"));
  assert.equal(manifest.scope, "/efhc/");
  assert.equal(manifest.id, "/efhc/");
  assert.ok(manifest.start_url.startsWith("/efhc/"));
  const worker = readFileSync(path.join(root, "sw.js"), "utf8");
  new vm.Script(worker);
  assert.match(worker, /const EFHC_PWA_BUILD_CONFIG =/);
  assert.ok(worker.includes("EFHC_HTML_GENERATION_MISMATCH"),
    "Bundled Workbox worker must refuse mixed-generation HTML");
  assert.ok(worker.includes("efhc-public-pages-"),
    "Bundled Workbox worker must use build-pinned offline page cache");
  assert.ok(!worker.includes("importScripts("),
    "The deployed Workbox runtime must be bundled locally without CDN scripts");
  const verify = run("verify_export.py", root);
  assert.equal(verify.status, 0, verify.stderr);
  const again = run("fix_pages_assets.py", root);
  assert.equal(again.status, 0, again.stderr);
  assert.equal(readFileSync(path.join(root, "sw.js"), "utf8"), worker, "same build must not prepend another config");
  assert.equal(readFileSync(path.join(root, "pwa-build.json"),"utf8"),JSON.stringify(config,null,2)+"\n","build manifest must remain deterministic");
  unlinkSync(path.join(root, "admin/users/index.html"));
  const rejected = run("verify_export.py", root);
  assert.notEqual(rejected.status, 0, "missing offline page must block deployment");
});

test("Public offline catalog never overwrites a verified newer response after mount", async () => {
  const { sourceRuntime } = await import("../helpers/source-runtime.mjs");
  const key = /const STORAGE_KEY = "([^"]+)"/.exec(read("src/lib/publicCatalogPersistence.ts"))?.[1];
  assert.ok(key, "Reuse the existing public catalogue storage identity");
  const timestamp = Date.now() - 60_000;
  const old = {items:[{sku:"previous"}]};
  const fresh = {items:[{sku:"current"}]};
  const storage = new Map([[key,JSON.stringify([{
    key:["tasksCatalog"],data:old,updatedAt:timestamp,
  }])]]);
  const runtime = sourceRuntime({storage,session:new Map()});
  const client = runtime.load("lib/queryClient.ts").createEfhcQueryClient();
  const catalog = runtime.load("lib/publicCatalogPersistence.ts");
  const queryKey = ["tasksCatalog"];
  client.setQueryData(queryKey,fresh,{updatedAt:Date.now()});
  catalog.hydratePublicCatalogQueries(client);
  assert.deepEqual(JSON.parse(JSON.stringify(client.getQueryData(queryKey))),fresh);
  // An empty in-memory query still receives the last valid offline catalog.
  client.removeQueries({queryKey});
  catalog.hydratePublicCatalogQueries(client);
  assert.deepEqual(JSON.parse(JSON.stringify(client.getQueryData(queryKey))),old);
  client.clear();
});

test("Existing USER data and local settings are retained rather than replaced by revalidation", () => {
  assert.match(read("src/lib/queryClient.ts"), /refetchOnMount: "always"/);
  assert.match(read("src/hooks/useSnapshot.ts"), /refetchOnMount: "always"/);
  assert.match(read("src/queries/usePanels.ts"), /refetchOnMount: "always"/);
  const settings = read("src/lib/settings.ts");
  const app = read("src/pages/_app.tsx");
  assert.match(app, /setSettingsHydrated\(true\)/);
  assert.match(app, /initialLocalSettingsRef/);
  assert.match(settings, /local choice made while the Telegram request was pending/i);
  assert.match(settings, /window\.localStorage\.getItem\(`\$\{KEY\}:\$\{owner\}`\)/);
  const ownerSwitch = read("src/lib/queryClient.ts");
  assert.match(ownerSwitch, /saveSettings\(resetSettings\(\)\)/);
  assert.doesNotMatch(ownerSwitch, /saveSettings\(loadSettings\(\)\)/);
  const activity = read("src/lib/frontendActivity.ts");
  assert.match(activity, /refetchQueries/);
  const energy = read("src/pages/index.tsx");
  assert.match(energy, /LIVE_TICK_MS = 333/);
  assert.match(energy, /performance\.now\(\)/);
});


test("Cached energy keeps a smooth local D8 display without extrapolating past the nearest panel expiry", async () => {
  const { sourceRuntime } = await import("../helpers/source-runtime.mjs");
  const h = sourceRuntime();
  const projection = h.load("lib/energyProjection.ts");
  assert.equal(projection.energyDisplayProjectionWindowMs("2026-11-07T12:00:00Z", "2026-11-07T12:00:45Z"), 45000);
  assert.equal(projection.energyDisplayProjectionWindowMs("2026-11-07T12:00:00Z", "2026-11-07T11:59:59Z"), 0);
  assert.equal(projection.energyDisplayProjectionWindowMs("invalid", "2026-11-07T12:00:45Z"), 0);
  assert.equal(projection.energyDisplayProjectionWindowMs("2026-11-07T12:00:00Z", null), Infinity);
  assert.ok(read("src/pages/index.tsx").includes("Math.min(projectUntilMs"), "Local projection must respect the expiry bound");
});

test("A newer local language/theme choice beats a pending older Telegram cloud response", async () => {
  const { sourceRuntime } = await import("../helpers/source-runtime.mjs");
  const owner = "0000000088";
  let releaseCloud;
  const cloudResponse = new Promise((resolve) => { releaseCloud = resolve; });
  const runtime = sourceRuntime({ overrides: {
    "./userDataCache": { currentUserDataOwner: () => owner },
    "./telegram": {
      telegramCloudStorageGet: () => cloudResponse,
      telegramCloudStorageSet: async () => undefined,
    },
  } });
  const settings = runtime.load("lib/settings.ts");
  const pending = settings.loadSettingsAsync();
  settings.saveSettings({ ...settings.resetSettings(), lang: "ru", color_theme_id: "CT-03" });
  releaseCloud(JSON.stringify({ ...settings.resetSettings(), lang: "en", color_theme_id: "CT-01" }));
  const selected = await pending;
  assert.equal(selected.lang, "ru");
  assert.equal(selected.color_theme_id, "CT-03");
  assert.equal(settings.loadSettings().color_theme_id, "CT-03");
});

test("A missing locale or theme asset aborts the full PWA install instead of reporting a ready offline shell", async () => {
  const source = read("public/sw.js");
  const events = new Map();
  const origin = "https://efhc.example";
  const scope = origin + "/efhc/";
  const stored = new Map();
  class RequestStub {
    constructor(value) { this.url = new URL(value, scope).href; }
  }
  const disk = {
    async match(req) { return stored.get(typeof req === "string" ? new URL(req, scope).href : req.url) || undefined; },
    async put(req, response) { stored.set(req.url, response.clone()); },
    async keys() { return [...stored.keys()].map(url => ({url})); },
    async delete(req) { return stored.delete(req.url); },
  };
  const worker = {
    registration: {scope, active:null},
    location: {origin},
    clients: {matchAll:async () => []},
    addEventListener(type, handler) {events.set(type,handler);},
  };
  const config = {
    build_id: "test-incomplete-locale",
    static_export: true,
    precache: ["/efhc/index.html","/efhc/locale/ru.json"],
    cache_limits: {
      static: {max_entries:100,max_age_seconds:2592000,max_bytes:16777216},
      content: {max_entries:100,max_age_seconds:604800,max_bytes:16777216},
    },
  };
  const sandbox = {
    self:worker, URL, Headers, Response, Blob, Request:RequestStub, Date, console,
    EFHC_PWA_BUILD_CONFIG:config,
    caches: {open:async () => disk,match:async req=>disk.match(req),keys:async()=>[],delete:async()=>true},
    fetch:async request => new Response(request.url.endsWith("ru.json") ? "missing" : '<html><meta name="efhc-build-id" content="test-incomplete-locale"></html>', {
      status:request.url.endsWith("ru.json") ? 404 : 200,
    }),
  };
  vm.runInNewContext(source,sandbox,{filename:"sw.js"});
  let installing;
  events.get("install")({waitUntil(promise){installing=promise;}});
  await assert.rejects(installing,/EFHC_REQUIRED_PRECACHE_FAILED/);
  assert.ok(stored.has(origin+"/efhc/index.html"),"valid page may stage, but worker must fail until locale is present");
});


// A controlling Service Worker owns an entire installed HTML/JS/CSS release.
// Online updates must NOT mix new HTML with the previously installed chunks.
test("PWA offline navigation opens a complete installed page without waiting for a worker update", async () => {
  const source = read("public/sw.js");
  const origin = "https://efhc.example";
  const scope = origin + "/efhc/";
  const cached = new Response("verified installed page", {status: 200});
  let updates = 0, network = 0;
  const sandbox = {
    URL, Response, Request, Headers, Blob, Date, console,
    self: {
      registration: {scope,active:{},update:async()=>{updates++;}},
      location:{origin},navigator:{onLine:false},
      addEventListener:()=>{},clients:{matchAll:async()=>[]},
    },
    EFHC_PWA_BUILD_CONFIG:{
      build_id:"current",static_export:true,precache:["/efhc/panels/index.html"],
      cache_limits:{static:{max_entries:100,max_age_seconds:2592000,max_bytes:10485760},
        content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880}},
    },
    caches:{
      match:async()=>undefined,
      open:async()=>({match:async url=>String(url).endsWith("/panels/index.html")?cached.clone():undefined}),
    },
    fetch:async()=>{network++;throw Error("offline transport");},
  };
  vm.runInNewContext(source+"\nthis.navigateForTest = navigationFallback;", sandbox);
  const holds=[];
  const response=await sandbox.navigateForTest(new Request(scope+"panels/"), {waitUntil:p=>holds.push(p)});
  assert.equal(await response.text(),"verified installed page");
  await Promise.all(holds);
  assert.equal(updates,0,"cached navigation must not keep an update fetch event alive");
  assert.match(read("src/components/PwaRuntimeStatus.tsx"), /trackedRegistration\.update\(\)/);
  assert.equal(network,0,"an offline navigation must not request network HTML");
  assert.match(source,/CLIENT_BUILD_READY/);
  assert.match(source,/EFHC_STALE_HTML_BUILD/);
  assert.match(source,/fetch\(request, \{cache: htmlDocument \? "no-store" : "reload"\}\)/);
  assert.match(source,/retireObsoleteBuildsIfSafe/);
});

test("Online navigation never combines next-release HTML with old controlling worker", async () => {
  const source = read("public/sw.js");
  const origin = "https://efhc.example";
  const scope = origin + "/efhc/";
  const oldPage = new Response('<meta name="efhc-build-id" content="old">OLD', {status:200});
  const newest = new Response('<meta name="efhc-build-id" content="new">LATEST', {status:200});
  let networkReads = 0;
  const cache = {match:async () => oldPage.clone()};
  const sandbox = {
    URL, Response, Request, Headers, Blob, Date, console,
    AbortController, setTimeout, clearTimeout,
    self:{
      registration:{scope,active:{}},location:{origin},navigator:{onLine:true},
      addEventListener:()=>{},clients:{matchAll:async()=>[]},
    },
    EFHC_PWA_BUILD_CONFIG:{
      build_id:"old",static_export:true,precache:["/efhc/index.html"],
      cache_limits:{static:{max_entries:100,max_age_seconds:2592000,max_bytes:10485760},
      content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880}},
    },
    caches:{open:async()=>cache,match:async()=>oldPage.clone()},
    fetch:async()=>{networkReads++;return newest.clone();},
  };
  vm.runInNewContext(source+"\nthis.navigateForTest = navigationFallback;",sandbox);
  const result=await sandbox.navigateForTest(new Request(scope),{waitUntil:()=>{}});
  assert.match(await result.text(),/OLD/,"old controller must serve its own verified HTML");
  assert.equal(networkReads,0,"a cached atomic release must not fetch a newer HTML document");
});

test("Evicted navigation recovers only from the controlling worker build",async()=>{
  const source=read("public/sw.js"),origin="https://efhc.example",scope=origin+"/efhc/";
  let onlineBuild="successor";
  const sandbox={
    URL,Response,Request,Headers,Blob,Date,console,AbortController,setTimeout,clearTimeout,
    self:{registration:{scope,active:{}},location:{origin},navigator:{onLine:true},
      addEventListener:()=>{},clients:{matchAll:async()=>[]}},
    EFHC_PWA_BUILD_CONFIG:{
      build_id:"installed",static_export:true,precache:["/efhc/withdraw/index.html"],
      cache_limits:{static:{max_entries:100,max_age_seconds:2592000,max_bytes:10485760},
        content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880}},
    },
    caches:{open:async()=>({match:async()=>undefined}),match:async()=>undefined},
    fetch:async()=>new Response('<meta name="efhc-build-id" content="'+onlineBuild+'">PAGE',{status:200}),
  };
  vm.runInNewContext(source+"\nthis.navigateForTest = navigationFallback;",sandbox);
  const request=new Request(scope+"withdraw/");
  const mismatched=await sandbox.navigateForTest(request,{waitUntil:()=>{}});
  assert.equal(mismatched.status,503,"a successor document must never run under an obsolete worker");
  onlineBuild="installed";
  const matched=await sandbox.navigateForTest(request,{waitUntil:()=>{}});
  assert.match(await matched.text(),/PAGE/,"network can restore only same-build HTML");
});

test("When online HTML is incomplete, keep the verified offline version", async () => {
  const source = read("public/sw.js");
  const origin = "https://efhc.example", scope = origin + "/efhc/";
  const verified = new Response("verified old offline page",{status:200});
  const sandbox = {
    URL,Response,Request,Headers,Blob,Date,console,AbortController,setTimeout,clearTimeout,
    self:{registration:{scope,active:{}},location:{origin},navigator:{onLine:true},
      addEventListener:()=>{},clients:{matchAll:async()=>[]}},
    EFHC_PWA_BUILD_CONFIG:{
      build_id:"old",static_export:true,precache:["/efhc/index.html"],
      cache_limits:{static:{max_entries:100,max_age_seconds:2592000,max_bytes:10485760},
      content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880}},
    },
    caches:{open:async()=>({match:async()=>verified.clone()}),match:async()=>verified.clone()},
    fetch:async()=>new Response("incomplete publication",{status:200}),
  };
  vm.runInNewContext(source+"\nthis.navigateForTest = navigationFallback;",sandbox);
  const result=await sandbox.navigateForTest(new Request(scope),{waitUntil:()=>{}});
  assert.equal(await result.text(),"verified old offline page");
});

test("active old worker never deletes a successor's staged build; new worker retires only prior caches", async () => {
  const source = read("public/sw.js");
  const origin = "https://efhc.example";
  const scope = origin + "/efhc/";
  const cacheNames = new Set(["efhc-pwa-old-static","efhc-pwa-old-content"]);
  const posted = [];
  const client = {id:"same-tab",url:scope,postMessage(message){posted.push(message)}};
  const oldClient = {id:"old-tab",url:scope+"panels/",postMessage(message){posted.push(message)}};
  let openClients = [client, oldClient];
  const buckets = new Map();
  const cacheStorage = {
    keys: async () => [...cacheNames],
    delete: async name => {buckets.delete(name);return cacheNames.delete(name);},
    open: async name => {
      cacheNames.add(name);
      if (!buckets.has(name)) buckets.set(name,new Map());
      const values = buckets.get(name);
      return {
        match: async req => values.get(String(req))?.clone(),
        put: async (req,response) => {values.set(String(req),response.clone());},
        keys: async () => [...values.keys()].map(url=>({url})),
      };
    },
    match: async () => undefined,
  };
  const makeWorker = buildId => {
    const events = new Map();
    const sandbox = {
      URL, Headers, Response, Request, Blob, Date, console,
      caches:cacheStorage,
      self:{
        registration:{scope,active:{}},
        location:{origin},
        clients:{
          matchAll:async()=>openClients,
          claim:async()=>undefined,
        },
        addEventListener:(type,listener)=>events.set(type,listener),
      },
      EFHC_PWA_BUILD_CONFIG:{
        build_id:buildId,static_export:true,
        precache:["/efhc/_next/static/"+buildId+".js"],
        cache_limits:{
          static:{max_entries:100,max_age_seconds:2592000,max_bytes:10485760},
          content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880},
        },
      },
    };
    vm.runInNewContext(source,sandbox,{filename:"sw.js"});
    const dispatch = async (type,options={}) => {
      let lifetime;
      const event={
        data:options.data,source:options.source,
        waitUntil:promise=>{lifetime=promise;},
      };
      events.get(type)(event);
      if(lifetime) await lifetime;
    };
    return {dispatch};
  };
  const oldStatic = await cacheStorage.open("efhc-pwa-old-static");
  await oldStatic.put("/efhc/index.html",new Response("verified old HTML"));
  const oldWorker = makeWorker("old");
  await oldWorker.dispatch("activate");
  // A successor preinstalls its static and content caches after the old
  // worker has already activated.
  cacheNames.add("efhc-pwa-next-static");
  cacheNames.add("efhc-pwa-next-content");
  await oldWorker.dispatch("message",{
    source:client,
    data:{
      type:"CLIENT_BUILD_READY",buildId:"old",
      assets:["/efhc/_next/static/old.js"],
    },
  });
  assert.equal(cacheNames.has("efhc-pwa-next-static"),true,
    "old active worker erased newly staged successor code");
  assert.equal(cacheNames.has("efhc-pwa-next-content"),true,
    "old active worker erased newly staged successor data");
  const newWorker = makeWorker("next");
  await newWorker.dispatch("activate");
  assert.equal(cacheNames.has("efhc-pwa-old-static"),true,
    "previous assets must survive until new client verifies its build");
  // Browsers regularly terminate a SW and then restart it WITHOUT an
  // activate event. Retirement inventory must be restored from CacheStorage.
  const resumedWorker = makeWorker("next");
  await resumedWorker.dispatch("message",{
    source:client,
    data:{
      type:"CLIENT_BUILD_READY",buildId:"next",
      assets:["/efhc/_next/static/next.js"],
    },
  });
  assert.equal(cacheNames.has("efhc-pwa-old-static"),true,
    "the old tab still needs its old immutable scripts");
  // The old tab is closed. A later status request from the verified new tab
  // rechecks retirement even though no activate event fires on the worker.
  openClients = [client];
  await resumedWorker.dispatch("message",{source:client,data:{type:"GET_CACHE_STATUS"}});
  assert.equal(cacheNames.has("efhc-pwa-old-static"),false,
    "a verified successor must retire the previous static build");
  assert.equal(cacheNames.has("efhc-pwa-old-content"),false,
    "a verified successor must retire the previous content build");
  assert.equal(cacheNames.has("efhc-pwa-next-static"),true,
    "the active successor's own assets must never be removed");
});

test("Android maskable icon preserves the canonical EFHC logo and safe zone", () => {
  const manifest = JSON.parse(read("public/manifest.webmanifest"));
  const regular = manifest.icons.filter((icon) => icon.purpose === "any");
  const maskable = manifest.icons.filter((icon) => icon.purpose === "maskable");
  assert.deepEqual(regular.map((icon) => icon.sizes), ["192x192", "512x512", "any"]);
  assert.deepEqual(regular[2], {
    src: "/assets/efhc/canon/efhc_logo_canon.svg",
    sizes: "any",
    type: "image/svg+xml",
    purpose: "any",
  });
  assert.equal(maskable.length, 1);
  assert.deepEqual(maskable[0], {
    src: "/assets/efhc/efhc_maskable.svg",
    sizes: "any",
    type: "image/svg+xml",
    purpose: "maskable",
  });
  const original = read("public/assets/efhc/canon/efhc_logo_canon.svg");
  const adaptive = read("public/assets/efhc/efhc_maskable.svg");
  const expected = original
    .replace(
      'width="8192" height="8192" viewBox="-163 -163 8518 8518"',
      'width="2048" height="2048" viewBox="-2048 -2048 12288 12288"',
    )
    .replace(
      '  <circle id="yellow-field"',
      '  <rect id="mask-background" x="-2048" y="-2048" width="12288" height="12288" fill="#000000" />\n  <circle id="yellow-field"',
    );
  assert.equal(adaptive, expected.replace(/C(?=\d)/g, "C "), "Android SVG must not alter the original logo geometry");
  assert.doesNotMatch(adaptive, /C\d{2,}/, "SVG path command must not resemble a program identifier");
  assert.ok(4163 < 0.4 * 12288, "EFHC outer ring must fit entirely inside the Android safe zone");
});

test("Profile PWA maintenance checks the registered worker without clearing account caches", () => {
  const settings = read("src/components/profile/ProfileSettingsDialog.tsx");
  assert.match(settings, /registration\.update\(\)/);
  assert.match(settings, /GET_CACHE_STATUS/);
  assert.match(settings, /pwa\.maintenance_title/);
  assert.doesNotMatch(settings, /localStorage\.clear\(|caches\.delete\(|indexedDB\.deleteDatabase\(/);
});

test("Android native splash follows the approved EFHC loading surface", () => {
  const manifest = JSON.parse(read("public/manifest.webmanifest"));
  const splash = read("src/components/SplashScreen.tsx");
  const maskable = read("public/assets/efhc/efhc_maskable.svg");
  assert.equal(manifest.background_color, "#000000");
  assert.equal(manifest.theme_color, "#000000");
  assert.match(splash, /bg-black transition-opacity/);
  assert.match(splash, /efhc_logo_canon\.svg/);
  assert.match(splash, /efhc-splash-progress/);
  assert.match(maskable, /id="mask-background"[^>]+fill="#000000"/);
});

test("Splash logo stays vector-sharp without GPU scale rasterization", () => {
  const splash = read("src/components/SplashScreen.tsx");
  const css = read("src/styles/globals.css");
  const start = css.indexOf("@keyframes efhc-splash-breathe{");
  const end = css.indexOf(".efhc-faq-shell{", start);
  assert.ok(start >= 0 && end > start, "The canonical splash animation is present");
  const animation = css.slice(start, end);
  assert.match(animation, /opacity:0\.94/);
  assert.doesNotMatch(animation, /transform|will-change/);
  assert.match(splash, /efhc_logo_canon\.svg/);
});
