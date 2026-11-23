/** Browser integration against the real Next static export and actual Chromium SW.
 * This is an ephemeral local Pages test; never publish, touch production,
 * prime financial data or grant Admin privileges.
 */
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir, unlink, utimes, stat } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { localPagesBase } from "./pages-base.mjs";

const { chromium } = createRequire(process.env.EFHC_BROWSER_TOOLS || import.meta.url)("playwright-core");
const base = localPagesBase();
const origin = new URL(base).origin;
const root = process.env.EFHC_PWA_EXPORT_DIR;
if (!root || !path.isAbsolute(root)) throw new Error("EFHC_PWA_EXPORT_DIR required");
const artifactDir = process.env.EFHC_PARITY_ARTIFACTS || "/tmp/efhc-persistence-artifacts";
const exportConfig = JSON.parse(await readFile(path.join(root,"pwa-build.json"),"utf8"));
// Resolve the persisted namespaces from their production owners: the browser
// test must not introduce duplicate version-labelled storage identities.
async function persistedKeyFromSource(filename) {
  const source = await readFile(new URL(`../../src/lib/${filename}`, import.meta.url), "utf8");
  const match = source.match(/\bconst KEY\s*=\s*["']([^"']+)["']\s*;/);
  assert.ok(match?.[1], `Production persistence key missing from ${filename}`);
  return match[1];
}
const ownerCacheKey = await persistedKeyFromSource("userDataCache.ts");
const settingsKey = await persistedKeyFromSource("settings.ts");
const authSessionKey = (await readFile(new URL("../../src/lib/auth-session.ts",import.meta.url),"utf8"))
  .match(/\bconst STORAGE_KEY\s*=\s*["']([^"']+)["']/)?.[1];
assert.ok(authSessionKey,"Auth credential storage key must be found in its owning source");
await mkdir(artifactDir, {recursive:true});
const browser = await chromium.launch({
  executablePath: process.env.CHROME_BIN || "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const context = await browser.newContext({
  viewport: {width:390,height:844},
  serviceWorkers: "allow",
});
let page = await context.newPage();
page.setDefaultTimeout(20000);
const results = [];
const errors = [];
page.on("pageerror", error => errors.push(String(error.message)));
await context.route("**/*", route => new URL(route.request().url()).origin === origin
  ? route.continue() : route.abort());
const boundedSerwistPhase = async (name, action, timeoutMs=15000) => {
  console.log("PWA_SERWIST_I35_BEGIN",name);
  let timer;
  try {
    const result=await Promise.race([
      Promise.resolve().then(action),
      new Promise((_,reject)=>{timer=setTimeout(()=>
        reject(Error("PWA_SERWIST_I35_TIMEOUT "+name+" "+timeoutMs+"ms")),timeoutMs);}),
    ]);
    console.log("PWA_SERWIST_I35_PASS",name);
    return result;
  } catch(error) {
    console.error("PWA_SERWIST_I35_FAIL",name,String(error));
    throw error;
  } finally {clearTimeout(timer);}
};

const verifyOfflineSplashReload=async(tab,phase)=>{
  // Playwright may report a null navigation response when Service Workers
  // handle the request. Prove a fresh document and the real EFHC splash,
  // not just a successful call to page.reload().
  await tab.evaluate(()=>{window.efhcOfflineReloadWitness=true;});
  let navigationError=null;
  try {
    await boundedSerwistPhase(phase,()=>tab.reload({
      waitUntil:"domcontentloaded",timeout:15000,
    }),19000);
  } catch(error) {navigationError=String(error);}
  // Chromium may commit a fresh offline SW document after Playwright has
  // rejected the navigation handle. Wait for the document proof itself:
  // the old page still has the witness and therefore cannot pass this gate.
  const documentProof=await boundedSerwistPhase(phase+".document.ready",()=>
    tab.waitForFunction(()=>window.efhcOfflineReloadWitness!==true &&
      Boolean(navigator.serviceWorker.controller) &&
      Boolean(document.querySelector(".efhc-entry-splash_content")),
      null,{timeout:12000}),16000);
  await documentProof.dispose();
  const state=await tab.evaluate(()=>({
    path:location.pathname,
    freshDocument:window.efhcOfflineReloadWitness!==true,
    controller:Boolean(navigator.serviceWorker.controller),
    controllerScript:navigator.serviceWorker.controller?.scriptURL||null,
    splash:Boolean(document.querySelector(".efhc-entry-splash_content")),
    title:document.title,
  })).catch(error=>({inspectionError:String(error)}));
  console.log("PWA_SERWIST_OFFLINE_RELOAD",phase,
    JSON.stringify({navigationError,state}));
  assert.equal(state.path,new URL(base).pathname+"offline.html");
  assert.equal(state.freshDocument,true,"Offline navigation must create a new document");
  assert.equal(state.controller,true,"The installed Serwist worker must control the offline page");
  assert.equal(new URL(state.controllerScript).pathname,
    new URL(base).pathname+"sw.js","The correct scoped worker must control the document");
  assert.equal(state.splash,true,"The existing EFHC splash must render offline");
  // Chromium sometimes reports ERR_ABORTED to Playwright even after it has
  // committed the new Service Worker document. A browser-level success is
  // proven above, independently of the nullable/rejected navigation handle.
  // Never accept any other navigation failure or a missing real document.
  if(navigationError) {
    assert.match(navigationError,/net::ERR_ABORTED/,
      "A non-abort browser navigation failure must fail the offline test");
    console.log("PWA_SERWIST_NAVIGATION_HANDLE_ABORTED_AFTER_DOCUMENT_COMMIT",phase);
  }
  return state;
};

const check = async (name,fn) => {
  await fn();
  results.push({name,status:"PASS"});
  console.log("PWA_INTEGRATION_PASS "+name);
};
try {
  await check("Serwist installs critical shell then resumes every required offline page in background", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const config = await (await page.request.get(base+"pwa-build.json")).json();
    assert.equal(config.static_export,true);
    assert.ok(config.precache.length > 40,"real export required");
    assert.ok(config.precache_critical.length > 4,"Serwist critical shell missing");
    assert.ok(config.precache_deferred.length > 0,"deferred export missing");
    await page.evaluate(() => Promise.race([
      navigator.serviceWorker.ready.then(() => true),
      new Promise((_,reject) => setTimeout(() => reject(Error("Serwist install timeout")),95000)),
    ]));
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller),null,{timeout:15000});
    const criticalState = await page.evaluate(async () => {
      const cfg = await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
      const keys = await caches.keys();
      const paths = new Set();
      for (const name of keys) {
        for (const req of await (await caches.open(name)).keys())
          paths.add(new URL(req.url).pathname);
      }
      return {keys,missing:cfg.precache_critical.filter(url=>!paths.has(url))};
    });
    assert.deepEqual(criticalState.missing,[],"Serwist must atomically cache critical shell before activation");
    assert.ok(criticalState.keys.some(name=>name.includes("precache")),
      "Serwist precache container missing");
    const requiredRouteAssets = config.precache.filter(url =>
      /\.(?:html|js|css)$/.test(url));
    assert.deepEqual(requiredRouteAssets.filter(url =>
      !config.precache_critical.includes(url)),[],
      "Route HTML, JS, and CSS must be installed before the new SW activates");
    // Ensure Energy is hydrated before making the old release's backend
    // unavailable. Offline route testing must not race initial React mount.
    await page.locator('[data-nav-key="nav.panels"]').waitFor({
      state:"visible",timeout:20000,
    });
    // Simulate a previous release's hashed files disappearing from Pages
    // before any optional background prefetch has completed.
    await context.setOffline(true);
    try {
      await page.locator('[data-nav-key="nav.panels"]').click();
      await page.getByRole("heading",{name:"Panels"}).waitFor({
        state:"visible",timeout:15000,
      });
      assert.equal(await page.locator(".efhc-entry-splash").count(),0,
        "An offline Energy-to-Panels transition must not strand the 8% splash");
      await page.locator('[data-nav-key="nav.exchange"]').click();
      await page.getByRole("heading",{name:"Exchange"}).waitFor({
        state:"visible",timeout:15000,
      });
      assert.equal(await page.locator(".efhc-entry-splash").count(),0,
        "An offline Panels-to-Exchange transition must retain React");
      console.log("PWA_SERWIST_CRITICAL_ROUTE_NAV_PASS",JSON.stringify({
        routeAssets:requiredRouteAssets.length,online:false,
      }));
    } finally {
      await context.setOffline(false);
      await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    }
    // No EFHC PREFETCH_PRIORITY/CACHE_COMPLETE controller remains. Ask the
    // *real* Serwist native CACHE_URLS handler to populate the public export,
    // then verify materialized CacheStorage entries rather than trusting a
    // synthetic completion event or disabling the offline safety assertion.
    const requested=await page.evaluate(async () => {
      const config=await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
      const deferred=config.precache_deferred.filter(url=>
        !url.endsWith(".mp3") &&
        !/\/(?:locale|faq)\/(?!en\.json$)[^/]+\.json$/.test(url));
      const controller=navigator.serviceWorker.controller;
      if (!controller)throw Error("Serwist controller required before native prefetch");
      controller.postMessage({type:"CACHE_URLS",payload:{urlsToCache:deferred}});
      return deferred;
    });
    await page.waitForFunction(async requested=>{
      const cached=new Set();
      for(const name of await caches.keys())
        for(const req of await (await caches.open(name)).keys())
          cached.add(new URL(req.url).pathname);
      return requested.every(url=>cached.has(url));
    },requested,{timeout:95000,polling:500});
    const info = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      const cfg = await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
      const cached = new Set();
      for (const name of await caches.keys()) {
        for (const req of await (await caches.open(name)).keys()) cached.add(new URL(req.url).pathname);
      }
      const required = cfg.precache.filter(url=>!url.endsWith(".mp3") &&
        !/\/(?:locale|faq)\/(?!en\.json$)[^/]+\.json$/.test(url));
      return {registered:Boolean(reg?.active),scope:reg?.scope,cachedCount:cached.size,
        missing:required.filter(url=>!cached.has(url)),cachedPaths:[...cached]};
    });
    assert.equal(info.registered,true);
    assert.equal(info.scope,base);
    assert.deepEqual(info.missing,[],"all application pages and non-on-demand resources must be available offline");
    for (const route of ["/panels/portfolio/index.html","/admin/index.html","/browser-shop/index.html"]) {
      assert.ok(info.cachedPaths.some(path=>path.endsWith(route)),"Offline page missing: "+route);
    }
    assert.ok(info.cachedPaths.some(path=>path.includes("/_next/static/")));
    assert.ok(info.cachedPaths.every(path=>!path.includes("/api/")&&!path.includes("runtime-config.json")),
      "never cache API/private credentials");
    results.push({name:"serwist_offline_inventory",status:"INFO",count:info.cachedCount});
  });
  await check("Cache click independently requests an update and foreground signals coalesce safely", async () => {
    const isolated=await browser.newContext({serviceWorkers:"allow",viewport:{width:390,height:844}});
    await isolated.route("**/*",route=>new URL(route.request().url()).origin===origin
      ? route.continue() : route.abort());
    const profile=await isolated.newPage();
    await profile.addInitScript(() => {
      const expected=new URL("/efhc/",location.origin).href;
      const state={calls:0,offset:0,activated:null,clearMode:"failed"};
      window.__efhcDiscoveryProof=state;
      const originalNow=Date.now;
      Date.now=()=>originalNow()+state.offset;
      const originalUpdate=ServiceWorkerRegistration.prototype.update;
      ServiceWorkerRegistration.prototype.update=function() {
        if(this.scope!==expected)return originalUpdate.call(this);
        state.calls++;
        return navigator.onLine ? Promise.resolve(this) : Promise.reject(new Error("synthetic offline"));
      };
      const originalPost=ServiceWorker.prototype.postMessage;
      ServiceWorker.prototype.postMessage=function(message,transfer) {
        if(message?.type!=="EFHC_PWA_EMERGENCY_CLEAR_CACHE"||!transfer?.[0])
          return originalPost.call(this,message,transfer);
        if(state.clearMode==="pending"){state.clearReply=transfer[0];return;}
        transfer[0].postMessage({status:state.clearMode});
      };
      window.Telegram={WebApp:{
        isVersionAtLeast:()=>true,
        onEvent:(name,handler)=>{if(name==="activated")state.activated=handler;},
        offEvent:(name,handler)=>{if(name==="activated"&&state.activated===handler)state.activated=null;},
      }};
    });
    try {
      await profile.goto(base+"web-profile/",{waitUntil:"domcontentloaded",timeout:30000});
      await profile.waitForFunction(()=>navigator.serviceWorker.controller&&window.__efhcDiscoveryProof.calls>=1&&window.__efhcDiscoveryProof.activated);
      await profile.locator('[data-profile-settings-entry="interface-card"]').click();
      const maintenance=profile.locator('[data-profile-settings-maintenance="visible"]');
      const button=maintenance.locator('[data-pwa-clear-public-cache="true"]');
      const calls=()=>profile.evaluate(()=>window.__efhcDiscoveryProof.calls);
      const incremented=count=>profile.waitForFunction(n=>window.__efhcDiscoveryProof.calls===n+1,count);
      for(const outcome of ["failed","empty","missing-controller","registering"]) {
        const before=await calls();
        await profile.evaluate(kind=>{
          const proof=window.__efhcDiscoveryProof;
          const sw=navigator.serviceWorker;
          delete sw.controller;
          delete sw.getRegistration;
          proof.clearMode=kind;
          if(kind==="missing-controller"||kind==="registering")
            Object.defineProperty(sw,"controller",{configurable:true,get:()=>null});
          if(kind==="registering")
            Object.defineProperty(sw,"getRegistration",{configurable:true,value:async()=>undefined});
        },outcome);
        await button.click();
        await incremented(before);
        const wording=outcome==="failed" ? /could not be confirmed|не удалось подтвердить/i
          : outcome==="empty" ? /public runtime cache cleared|кеш очищен/i
          : /unavailable in this browser|недоступно в этом браузере/i;
        await maintenance.getByRole("status").filter({hasText:wording}).waitFor({state:"visible"});
        await button.waitFor({state:"visible"});
        assert.equal(await button.isEnabled(),true);
      }
      await profile.evaluate(()=>{
        const sw=navigator.serviceWorker;delete sw.controller;delete sw.getRegistration;
        window.__efhcDiscoveryProof.clearMode="failed";
      });
      await isolated.setOffline(true);
      await profile.waitForFunction(()=>!navigator.onLine);
      const offlineBefore=await calls();
      await button.click();
      await incremented(offlineBefore);
      await isolated.setOffline(false);
      await incremented(offlineBefore+1);
      // Keep the real button handler pending beyond the ordinary idle cutoff.
      const pendingBefore=await calls();
      await profile.evaluate(()=>{window.__efhcDiscoveryProof.clearMode="pending";});
      await button.click();
      await incremented(pendingBefore);
      await profile.waitForFunction(()=>Boolean(window.__efhcDiscoveryProof.clearReply));
      const reportsSafe=()=>profile.evaluate(()=>new Promise((resolve,reject)=>{
        const channel=new MessageChannel();
        const timeout=setTimeout(()=>reject(new Error("Missing page safety reply")),3000);
        channel.port1.onmessage=event=>{
          clearTimeout(timeout);channel.port1.close();resolve(event.data?.safe);
        };
        navigator.serviceWorker.dispatchEvent(new MessageEvent("message",{
          data:{type:"EFHC_PWA_CLIENT_SAFE",purpose:"upgrade"},ports:[channel.port2],
        }));
      }));
      await profile.evaluate(()=>{window.__efhcDiscoveryProof.offset+=7000;});
      assert.equal(await reportsSafe(),false,"Discovery must not let reload overtake pending cleanup");
      await profile.evaluate(()=>{
        const proof=window.__efhcDiscoveryProof;
        proof.clearReply.postMessage({status:"failed"});
        proof.clearReply.close();
      });
      await maintenance.getByRole("status").filter({hasText:/could not be confirmed|не удалось подтвердить/i}).waitFor({state:"visible"});
      assert.equal(await reportsSafe(),true,"A completed cleanup releases only its own hold");
      // Test every public platform signal separately and a burst together.
      for(const event of ["focus","resume","activated","burst"]) {
        const before=await calls();
        await profile.evaluate(name=>{
          const proof=window.__efhcDiscoveryProof;
          proof.offset+=21000;
          if(name==="focus"||name==="burst")window.dispatchEvent(new Event("focus"));
          if(name==="resume"||name==="burst")document.dispatchEvent(new Event("resume"));
          if(name==="activated"||name==="burst")proof.activated?.();
        },event);
        await incremented(before);
        assert.equal(await calls(),before+1);
      }
      const withinCooldown=await calls();
      await profile.evaluate(() => {
        window.__efhcDiscoveryProof.offset+=19_200;
        document.dispatchEvent(new Event("resume"));
        document.dispatchEvent(new Event("resume"));
      });
      assert.equal(await calls(),withinCooldown,"A burst within the interval is not sent immediately");
      await incremented(withinCooldown);
      console.log("PWA_FOREGROUND_AND_EXPLICIT_DISCOVERY_PASS");
    } finally {await isolated.close();}
  });
  await check("rendered public CSS links use content-addressed paths for every root stylesheet", async () => {
    await page.locator("#__next").waitFor({state:"attached"});
    const links = await page.evaluate(() => [...document.querySelectorAll("link[rel='stylesheet'][href]")]
      .map(link => new URL(link.href).pathname)
      .filter(name => name.startsWith("/efhc/") &&
        !name.includes("/_next/") && name.endsWith(".css")));
    assert.ok(links.length > 0, "Expected public visual stylesheet links");
    for (const link of links) {
      assert.match(link,/\.[a-f0-9]{16}\.css$/,"Public CSS is not release-specific: "+link);
      assert.ok(exportConfig.precache.includes(link),"Hashed public stylesheet missing from cache: "+link);
    }
  });
  await check("fresh browser tab restores device visual choices offline without an owner hint", async () => {
    // This uses only non-sensitive display preferences: no authenticated
    // account, financial payload, operator credential or fake Global ID.
    const previous = await page.evaluate(() => {
      const key = "EFHC_DEVICE_VIEW_PREFERENCES";
      const old = localStorage.getItem(key);
      localStorage.setItem(key, JSON.stringify({
        interface_settings_version:4,lang:"ru",color_theme_id:"CT-03",
        global_theme_id:"03",theme_mode:"dark",music_enabled:false,
      }));
      return old;
    });
    const second = await context.newPage();
    second.setDefaultTimeout(12000);
    try {
      await context.setOffline(true);
      await second.goto(base,{waitUntil:"domcontentloaded",timeout:25000});
      await second.locator('[data-theme-page-surface="true"][data-color-theme-id="CT-03"]')
        .first().waitFor({state:"attached",timeout:12000});
      const state = await second.evaluate(() => ({
        lang:document.documentElement.lang,
        color:document.querySelector('[data-theme-page-surface="true"]')?.getAttribute("data-color-theme-id"),
        leakedOwner:sessionStorage.getItem("efhc:resolved-display-owner"),
        shell:document.querySelector("#__next")?.innerHTML.length || 0,
      }));
      assert.equal(state.lang,"ru");
      assert.equal(state.color,"CT-03");
      assert.equal(state.leakedOwner,null,"a new browser tab must not inherit a validated owner");
      assert.ok(state.shell>100,"real React shell must not await backend bootstrap");
    } finally {
      await context.setOffline(false);
      await second.close();
      await page.evaluate(previous => {
        if(previous===null)localStorage.removeItem("EFHC_DEVICE_VIEW_PREFERENCES");
        else localStorage.setItem("EFHC_DEVICE_VIEW_PREFERENCES",previous);
      },previous).catch(()=>undefined);
    }
  });
  await check("verified same-tab owner restores last read-only snapshot offline on reload", async () => {
    // A real same-tab reload retains the signed-session-derived display owner.
    // A different tab does not inherit that marker (tested above). This fixture
    // is local test data, never a real user, network response or credential.
    const owner = "0000000042";
    const expected = "204.00000000";
    const saved = await page.evaluate(({owner,cacheKey}) => {
      const ownerKey = "efhc:resolved-display-owner";
      const entries = [ownerKey,cacheKey];
      const previous = Object.fromEntries(entries.map(key => [key,sessionStorage.getItem(key)]));
      const durableKey = cacheKey + ":" + owner;
      const oldDurable = localStorage.getItem(durableKey);
      const snapshot = {
        profile:{
          global_id:owner,username:"Offline Owner",is_vip:false,has_activ:false,
          main_balance:"200.00000000",bonus_balance:"4.00000000",
          available_kwh:"12.00000000",total_generated_kwh:"6.00000000",
          gen_per_sec_base:"0.00000000",gen_per_sec_vip:"0.00000000",
        },
        panels:{active_count:2,total_generated_by_panels:"0.00000000",nearest_expire_at:null},
        exchange_preview:{ok:true,available_kwh:"12.00000000",
          max_exchangeable_kwh:"12.00000000",rate_kwh_to_efhc:"1.00000000",detail:""},
        meta:{server_now_iso:"2026-11-08T00:00:00Z",gen_per_sec_effective:"0.00000000",
          next_scheduler_eta_sec:0,fallback_task_id:null},
      };
      sessionStorage.setItem(ownerKey,JSON.stringify({global_id:owner,principal:"browser"}));
      sessionStorage.setItem(cacheKey,JSON.stringify({owner,entries:[]}));
      localStorage.setItem(durableKey,JSON.stringify({owner,entries:[
        {key:["syncSnapshot",owner],data:snapshot,updatedAt:Date.now()-2000},
      ]}));
      return {previous,oldDurable,durableKey};
    },{owner,cacheKey:ownerCacheKey});
    await context.setOffline(true);
    try {
      await page.reload({waitUntil:"domcontentloaded",timeout:30000});
      await page.locator('[data-header-balance-value="204.00000000"]').first()
        .waitFor({state:"attached",timeout:12000});
      const state = await page.evaluate(({owner,expected,authKey}) => ({
        owner:JSON.parse(sessionStorage.getItem("efhc:resolved-display-owner")||"null")?.global_id,
        displayed:document.querySelector('[data-balance-scope="global-header"]')?.getAttribute("data-header-balance-density"),
        balance:document.querySelector("[data-header-balance-value]")?.getAttribute("data-header-balance-value"),
        shell:document.querySelector("#__next")?.innerHTML.length||0,
        // This is a read-only cached display. No signed write is authorized.
        authToken:sessionStorage.getItem(authKey),
      }),{owner,expected,authKey:authSessionKey});
      assert.equal(state.owner,owner);
      assert.equal(state.balance,expected);
      assert.ok(state.shell>100);
      assert.equal(state.authToken,null);
    } finally {
      await context.setOffline(false);
      await page.evaluate(({saved,cacheKey}) => {
        for(const [key,value] of Object.entries(saved.previous)) {
          if(value===null)sessionStorage.removeItem(key);
          else sessionStorage.setItem(key,value);
        }
        if(saved.oldDurable===null)localStorage.removeItem(saved.durableKey);
        else localStorage.setItem(saved.durableKey,saved.oldDurable);
      },{saved,cacheKey:ownerCacheKey}).catch(()=>undefined);
      await page.reload({waitUntil:"domcontentloaded",timeout:30000});
    }
  });
  await check("offline Withdraw keeps its form when stored financial read shapes are obsolete", async () => {
    const owner = "0000000042";
    const saved = await page.evaluate(({owner,cacheKey}) => {
      const markerKey = "efhc:resolved-display-owner";
      const durableKey = cacheKey + ":" + owner;
      const prior = {
        marker: sessionStorage.getItem(markerKey),
        tab: sessionStorage.getItem(cacheKey),
        durable: localStorage.getItem(durableKey),
        durableKey,
      };
      const snapshot = {
        profile: {
          global_id:owner,username:"Offline Owner",is_vip:false,has_activ:false,
          main_balance:"801.00000000",bonus_balance:"0.00000000",
          available_kwh:"0.00000000",total_generated_kwh:"0.00000000",
          gen_per_sec_base:"0.00000692",gen_per_sec_vip:"0.00000741",
        },
        panels:{active_count:0,total_generated_by_panels:"0.00000000",nearest_expire_at:null},
        exchange_preview:{ok:true,available_kwh:"0.00000000",
          max_exchangeable_kwh:"0.00000000",rate_kwh_to_efhc:"1.00000000",detail:""},
        meta:{server_now_iso:"2026-11-13T00:00:00Z",
          gen_per_sec_effective:"0.00000692",next_scheduler_eta_sec:0,fallback_task_id:null},
      };
      const stored = {owner,lastHumanVisitAt:Date.now(),entries:[
        {key:["syncSnapshot",owner],data:snapshot,updatedAt:Date.now()-2000},
        {key:["withdrawals",owner,"list","all"],
          data:{pages:{items:[]}},updatedAt:Date.now()-2000},
        {key:["withdrawals",owner,"balance-history"],
          data:[null],updatedAt:Date.now()-2000},
      ]};
      sessionStorage.setItem(markerKey,JSON.stringify({global_id:owner,principal:"browser"}));
      sessionStorage.setItem(cacheKey,JSON.stringify(stored));
      localStorage.setItem(durableKey,JSON.stringify(stored));
      return prior;
    },{owner,cacheKey:ownerCacheKey});
    await context.setOffline(true);
    try {
      await page.goto(base+"withdraw/",{waitUntil:"domcontentloaded",timeout:30000});
      await page.locator('[data-public-surface="withdraw"]').waitFor({
        state:"attached",timeout:16000,
      });
      const state = await page.evaluate(cacheKey => {
        const restored = JSON.parse(sessionStorage.getItem(cacheKey) || "null");
        return {
          active:document.querySelector('[data-public-surface="withdraw"]') !== null,
          error:document.querySelector('[data-safe-error-state]') !== null,
          balance:document.querySelector('[data-header-balance-value]')?.getAttribute("data-header-balance-value"),
          owner:restored?.owner,
          invalid:restored?.entries?.some(entry=>entry?.key?.[0]==="withdrawals"),
        };
      },ownerCacheKey);
      assert.equal(state.active,true,"Withdraw page must not be replaced by a generic error");
      assert.equal(state.error,false,"The failed cache read must not render the 500 surface");
      assert.equal(state.balance,"801.00000000","Valid same-owner balance must survive cache filtering");
      assert.equal(state.owner,owner,"Hydration must validate the actual owner");
      assert.equal(state.invalid,false,"Malformed Withdraw queries must not be rehydrated");
    } finally {
      await context.setOffline(false);
      await page.evaluate(({saved,cacheKey}) => {
        if (saved.marker===null)sessionStorage.removeItem("efhc:resolved-display-owner");
        else sessionStorage.setItem("efhc:resolved-display-owner",saved.marker);
        if (saved.tab===null)sessionStorage.removeItem(cacheKey);
        else sessionStorage.setItem(cacheKey,saved.tab);
        if (saved.durable===null)localStorage.removeItem(saved.durableKey);
        else localStorage.setItem(saved.durableKey,saved.durable);
      },{saved,cacheKey:ownerCacheKey}).catch(()=>undefined);
      await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    }
  });
  await check("older Telegram WebView keeps cached Withdraw requests and static controls", async () => {
    const owner = "0000000042";
    const webviewTab = await context.newPage();
    webviewTab.on("pageerror", error => errors.push(String(error.message)));
    try {
      await webviewTab.goto(base, {waitUntil:"domcontentloaded",timeout:30000});
      await webviewTab.evaluate(({owner,cacheKey}) => {
        const stored = {owner,lastHumanVisitAt:Date.now(),entries:[{
          key:["withdrawals",owner,"list","all"],
          data:{
            pages:[{items:[{
              id:"1",global_id:owner,amount:"10.00000000",status:"PENDING",
              created_at:"2026-11-14T00:00:00Z",
              updated_at:"2026-11-14T00:00:00Z",
            }],next_cursor:null}],
            pageParams:[null],
          },
          updatedAt:Date.now()-2000,
        }]};
        sessionStorage.setItem("efhc:resolved-display-owner",JSON.stringify({
          global_id:owner,principal:"browser",
        }));
        sessionStorage.setItem(cacheKey,JSON.stringify(stored));
        localStorage.setItem(cacheKey+":"+owner,JSON.stringify(stored));
      },{owner,cacheKey:ownerCacheKey});
      // Model an older Android WebView whose array .at() API is absent.
      // This does not claim to reproduce the OWNER's native Telegram engine.
      await webviewTab.addInitScript(() => {
        Object.defineProperty(Array.prototype,"at",{
          configurable:true,writable:true,value:undefined,
        });
      });
      await context.setOffline(true);
      await webviewTab.goto(base+"withdraw/",{waitUntil:"domcontentloaded",timeout:30000});
      await webviewTab.locator('[data-public-surface="withdraw"]').waitFor({
        state:"visible",timeout:16000,
      });
      await webviewTab.locator('[data-withdraw-request-id="1"]').waitFor({
        state:"attached",timeout:16000,
      });
      const view=await webviewTab.evaluate(() => ({
        alive:Boolean(document.querySelector('[data-public-surface="withdraw"]')),
        form:Boolean(document.querySelector('[data-withdraw-amount-input]')),
        requests:document.querySelectorAll('[data-withdraw-request-id]').length,
        error:document.body.textContent?.includes("Application error: a client-side exception") || false,
      }));
      assert.equal(view.alive,true,"Withdraw static page must remain mounted");
      assert.equal(view.form,true,"The existing withdraw input must remain");
      assert.equal(view.requests,1,"Cached confirmed read-only requests must render");
      assert.equal(view.error,false,"Next.js technical exception must not replace Withdraw");
    } finally {
      await context.setOffline(false);
      await webviewTab.close();
    }
  });
  await check("offline deep links use cached React UI instead of offline fallback", async () => {
    await page.reload({waitUntil:"domcontentloaded",timeout:30000});
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller),null,{timeout:15000});
    await context.setOffline(true);
    for(const route of ["","panels/portfolio/","faq/","hub/","admin/","browser-shop/"]){
      await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
      const rendered = await page.evaluate(() => ({
        title:document.title,
        size:document.getElementById("__next")?.innerHTML.length||0,
        text:document.body.innerText.slice(0,2200),
        worker:Boolean(navigator.serviceWorker.controller),
      }));
      assert.equal(rendered.worker,true,"SW controller lost for "+route);
      assert.ok(rendered.size>100,"React shell missing for "+route);
      assert.ok(!rendered.text.includes("EFHC is offline."),"technical fallback replaced route "+route);
      assert.ok(!rendered.text.includes("Application error"),"React error for "+route);
      console.log("PWA_OFFLINE_ROUTE_OK "+(route||"home"));
    }
    await context.setOffline(false);
  });
  await check("every exported application HTML route remains navigable without transport", async () => {
    const htmlRoutes = exportConfig.precache.filter(url =>
      url.endsWith(".html") && !/\/offline(?:-readonly)?\.html$/.test(url));
    // The old 42-route floor counted Next's generated 404/index.html. EFHC
    // deliberately removes that unapproved technical route from the export.
    assert.ok(htmlRoutes.length >= 41,"all 41 approved Next routes are required, not just six smoke pages");
    assert.ok(!htmlRoutes.some(route => /\/(?:404|500)\/(?:index\.html)?$/.test(route)),
      "retired technical error routes must not reappear in the cached page set");
    await context.setOffline(true);
    try {
      for (const html of htmlRoutes) {
        const destination = html.endsWith("/index.html") ? html.slice(0,-"index.html".length) : html;
        await page.goto(new URL(destination,origin).href,{waitUntil:"domcontentloaded",timeout:25000});
        const view = await page.evaluate(() => ({
          controlled:Boolean(navigator.serviceWorker.controller),
          reactRoot:Boolean(document.querySelector("#__next")),
          bodySize:document.body.innerText.length,
          fallback:document.body.innerText.includes("EFHC is offline."),
        }));
        assert.ok(view.controlled && view.reactRoot && view.bodySize>10 && !view.fallback,
          "offline route shell failed: "+JSON.stringify({destination,view}));
      }
    } finally { await context.setOffline(false); }
    console.log("PWA_ALL_EXPORTED_ROUTES_OK "+htmlRoutes.length);
    results.push({name:"all_exported_routes_inventory",status:"INFO",count:htmlRoutes.length});
  });
  await check("offline reload restores local language, CT theme and audio choices before backend", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    // A real user choice first updates React state, which then persists it.
    // Writing sessionStorage without notifying a mounted app creates an invalid
    // race: its previous in-memory settings can overwrite the injected value.
    await page.waitForFunction(() => Boolean(document.documentElement.dataset.efhcLocale),null,{timeout:15000});
    await page.evaluate(({ownerCacheKey,settingsKey}) => {
      // Restore for the currently active *display owner*, if there is one;
      // never inject another Global ID or create an authorization fixture.
      const cacheOwner=JSON.parse(sessionStorage.getItem(ownerCacheKey)||"null")?.owner||null;
      sessionStorage.setItem(settingsKey,JSON.stringify({
        settings_owner:cacheOwner,lang:"ru",color_theme_id:"CT-03",global_theme_id:"03",
        theme_mode:"dark",music_enabled:true,sfx_enabled:false,reduce_motion:false,
        interface_settings_version:4,
      }));
      window.dispatchEvent(new Event("efhc:user-settings-ready"));
    },{ownerCacheKey,settingsKey});
    await page.locator('[data-theme-page-surface="true"][data-color-theme-id="CT-03"]').first().waitFor({state:"attached",timeout:15000});
    await context.setOffline(true);
    try {
      for (const route of ["","panels/",""]) {
        await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
        // Editing-only theme dots are absent in normal USER mode. Verify the
        // real, rendered USER shell color token rather than a hidden editor.
        await page.locator('[data-theme-page-surface="true"][data-color-theme-id="CT-03"]').first().waitFor({state:"attached",timeout:15000});
        assert.equal(await page.locator("html").getAttribute("data-efhc-locale"),"ru","offline app must hydrate saved locale");
        const settings=await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)||"null"),settingsKey);
        assert.equal(settings?.lang,"ru");
        assert.equal(settings?.color_theme_id,"CT-03");
        assert.equal(settings?.music_enabled,true);
        assert.equal(settings?.sfx_enabled,false);
        if (!route) {
          await page.locator(".efhc-energy-stage_eyebrow").waitFor({state:"visible",timeout:15000});
          // The root locale can update before React commits translated text.
          // Require the actual USER caption, never just the locale attribute.
          await page.waitForFunction(() =>
            document.querySelector(".efhc-energy-stage_eyebrow")?.textContent?.trim() === "Энергия",
            null, {timeout:15000});
          const title=(await page.locator(".efhc-energy-stage_eyebrow").innerText()).trim();
          assert.equal(title,"Энергия","visible language must match cached Russian preference");
        }
      }
    } finally { await context.setOffline(false); }
  });
  await check("all ten color themes keep Energy and Referrals progress within rails offline", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const previous=await page.evaluate(key=>sessionStorage.getItem(key),settingsKey);
    const themes=Array.from({length:10},(_,i)=>"CT-"+String(i+1).padStart(2,"0"));
    let verified=0;
    await context.setOffline(true);
    try {
      for(const ct of themes){
        await page.evaluate(({key,ct})=>{
          const current=JSON.parse(sessionStorage.getItem(key)||"null");
          if(!current) throw Error("Expected cached UI settings before theme progress sweep");
          current.color_theme_id=ct;
          current.global_theme_id=ct.slice(3);
          sessionStorage.setItem(key,JSON.stringify(current));
          window.dispatchEvent(new Event("efhc:user-settings-ready"));
        },{key:settingsKey,ct});
        for(const route of ["","referrals/"]){
          await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
          await page.locator(`[data-theme-page-surface="true"][data-color-theme-id="${ct}"]`).first().waitFor({state:"attached",timeout:12000});
          for(const width of [390,1440]){
            await page.setViewportSize({width,height:900});
            const selectors=route
              ? [".efhc-energy-progress-track",".efhc-referral-achievement-track"]
              : [".efhc-energy-progress-track"];
            for(const selector of selectors){
              const track=page.locator(selector).first();
              await track.waitFor({state:"attached",timeout:12000});
              const box=await track.evaluate(el=>{
                const rail=el.getBoundingClientRect(),fill=el.firstElementChild?.getBoundingClientRect();
                return {rail:rail.width,fill:fill?.width??-1,inline:el.firstElementChild?.style?.width??""};
              });
              assert.ok(Number.isFinite(box.rail)&&box.rail>0 &&
                Number.isFinite(box.fill)&&box.fill>=0&&box.fill<=box.rail+2 &&
                !/(?:NaN|Infinity|undefined)/.test(box.inline),
                "theme progress overflow "+JSON.stringify({ct,route,width,selector,box}));
              verified++;
            }
          }
        }
      }
    }finally{
      await page.evaluate(({key,previous})=>{if(previous===null)sessionStorage.removeItem(key);
        else sessionStorage.setItem(key,previous);},{key:settingsKey,previous}).catch(()=>undefined);
      await context.setOffline(false);
    }
    console.log("PWA_ALL_CT_PROGRESS_OK "+verified);
    results.push({name:"ten_theme_progress_inventory",status:"INFO",count:verified});
  });
  await check("one-pixel frame CSS stays cached and paints offline", async () => {
    const framePath = exportConfig.precache.find(asset =>
      /\/frame-thickness-contract\.[a-f0-9]{16}\.css$/.test(asset));
    assert.ok(framePath, "1px frame contract must have a hashed URL in full offline precache");
    await context.setOffline(true);
    try {
      await page.goto(base, { waitUntil: "domcontentloaded", timeout: 25000 });
      await page.waitForFunction(cssPath => [...document.styleSheets].some(sheet =>
        sheet.href && new URL(sheet.href).pathname === cssPath), framePath, { timeout: 12000 });
      const proof = await page.evaluate(async (cssPath) => {
         const cachesList = await caches.keys();
        let cached = false;
        for (const name of cachesList) {
          const cache = await caches.open(name);
          for (const request of await cache.keys()) {
            if (new URL(request.url).pathname === cssPath) {
              cached = true;
              break;
            }
          }
        }
        const coin = document.querySelector(".efhc-independent-shell[data-interface-app-mode='user'] .efhc-energy-stage_coin");
        if (!coin) throw Error("Missing rendered Energy coin for offline CSS check");
        const before = coin.getAttribute("data-ei");
        try {
          coin.setAttribute("data-ei", "EI-15");
          const computed = getComputedStyle(coin);
          return {cached, border: computed.borderTopWidth, style: computed.borderTopStyle};
        } finally {
          if (before == null) coin.removeAttribute("data-ei");
          else coin.setAttribute("data-ei", before);
        }
      }, framePath);
      assert.equal(proof.cached, true, "1px CSS absent from offline static cache");
      assert.equal(proof.border, "1px", "cached 1px frame contract not applied offline");
      assert.equal(proof.style, "solid");
    } finally {
      await context.setOffline(false);
    }
  });
  await check("offline progress indicators stay finite and inside their tracks at 390/1440", async () => {
    await context.setOffline(true);
    try {
      for (const width of [390,1440]) {
        await page.setViewportSize({width,height:900});
        for (const [route,selector] of [
          ["",".efhc-energy-progress-track"],
          ["referrals/",".efhc-energy-progress-track"],
          ["referrals/",".efhc-referral-achievement-track"],
        ]) {
          await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
          await page.locator(selector).first().waitFor({state:"attached"});
          const data = await page.locator(selector).first().evaluate(track=>{
            const fill = track.firstElementChild;
            const rail = track.getBoundingClientRect();
            const widthCss = fill ? getComputedStyle(fill).width : "";
            const fillRect = fill?.getBoundingClientRect();
            return {rail:rail.width,paint:fillRect?.width ?? 0,widthCss,
              inline:fill?.style?.width ?? "",child:Boolean(fill)};
          });
          assert.equal(data.child,true,route+" "+selector+" has no progress fill");
          assert.ok(Number.isFinite(data.rail) && data.rail>=0);
          assert.ok(Number.isFinite(data.paint) && data.paint>=0 && data.paint<=data.rail+2,
            "progress fill escapes rail "+JSON.stringify({width,route,selector,data}));
          assert.ok(!/(NaN|Infinity|undefined)/i.test(data.inline),
            "invalid progress percentage "+JSON.stringify({width,route,selector,data}));
        }
        const values = await page.locator("[role=progressbar][aria-valuenow]").evaluateAll(nodes=>
          nodes.map(n=>({name:n.getAttribute("aria-label"),value:Number(n.getAttribute("aria-valuenow"))})));
        for (const item of values) assert.ok(Number.isFinite(item.value) && item.value>=0 && item.value<=100,
          "invalid accessibility percentage "+JSON.stringify(item));
      }
    } finally { await context.setOffline(false); }
  });
  await check("cold offline reopen restores app shell and interactive PNL tabs without network", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    await page.close();
    await context.setOffline(true);
    try {
      // A new browser tab is a new application open; Service Worker/CacheStorage
      // survive while the old page and its JavaScript heap no longer exist.
      page=await context.newPage();
      page.on("pageerror",error=>errors.push(String(error.message)));
      await page.goto(base+"panels/portfolio/",{waitUntil:"load",timeout:30000});
      const before=await page.evaluate(()=>({
        sw:Boolean(navigator.serviceWorker.controller),
        app:document.querySelector("#panelsPortfolioPage")!==null,
        cachePresent:Boolean(window.caches),
      }));
      assert.equal(before.sw,true);
      assert.equal(before.app,true);
      assert.equal(before.cachePresent,true);
      await page.locator('[data-panels-tab-button="archive"]').waitFor({state:"visible",timeout:12000});
      await page.waitForTimeout(400); // Give React an event-loop turn to finish hydration.
      await page.locator('[data-panels-tab-button="archive"]').click();
      await page.locator('[data-panels-tab-button="archive"][data-active="true"]').waitFor({
        state:"attached",timeout:10000,
      });
      await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
      await page.locator(".efhc-energy-stage").waitFor({state:"visible",timeout:12000});
    } finally { await context.setOffline(false); }
  });
  await check("An already-started locale response cannot rewrite public CacheStorage after an emergency purge", async () => {
    const race=await browser.newContext({serviceWorkers:"allow"});
    const release=Promise.withResolvers();
    const intercepted=Promise.withResolvers();
    const localeCache="efhc-serwist-locale";
    const probe=base+"locale/efhc-purge-overlap-proof.json";
    const stale=base+"locale/efhc-purge-old-proof.json";
    const scopeMarker="efhc-purge-proof-retention";
    let networkCalls=0;
    await race.route("**/*", route=>new URL(route.request().url()).origin===origin
      ? route.continue() : route.abort());
    await race.route(probe,async route=>{
      assert.ok(route.request().serviceWorker(),"The held network response must belong to Serwist");
      if(++networkCalls===1){
        intercepted.resolve();
        await release.promise;
      }
      await route.fulfill({contentType:"application/json",status:200,
        body:JSON.stringify({marker:networkCalls===1?"before-purge":"after-purge"})});
    });
    try {
      const tab=await race.newPage();
      await tab.goto(base,{waitUntil:"load",timeout:30000});
      await tab.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),null,{timeout:20000});
      await tab.evaluate(async ({localeCache,stale,scopeMarker})=>{
        sessionStorage.setItem(scopeMarker,"keep");
        await (await caches.open(localeCache)).put(stale,new Response("old-translation"));
        await (await caches.open(scopeMarker)).put(stale,new Response("other-app"));
      },{localeCache,stale,scopeMarker});
      await tab.evaluate(probe=>{
        window.efhcPurgeRace=fetch(probe).then(response=>response.json());
      },probe);
      let deadline;
      try {
        await Promise.race([intercepted.promise,new Promise((_,reject)=>{
          deadline=setTimeout(()=>reject(Error("Serwist did not start the public locale request")),4000);
        })]);
      } finally {clearTimeout(deadline);}
      const cleared=await tab.evaluate(async ()=>{
        const channel=new MessageChannel();
        const result=new Promise((resolve,reject)=>{
          const timer=setTimeout(()=>{channel.port1.close();reject(Error("Emergency purge reply timeout"));},8000);
          channel.port1.onmessage=event=>{
            clearTimeout(timer);channel.port1.close();resolve(event.data);
          };
        });
        navigator.serviceWorker.controller.postMessage(
          {type:"EFHC_PWA_EMERGENCY_CLEAR_CACHE"},[channel.port2]);
        return result;
      });
      assert.equal(cleared.status,"cleared",JSON.stringify(cleared));
      release.resolve();
      assert.deepEqual(await tab.evaluate(()=>window.efhcPurgeRace),
        {marker:"before-purge"},"Purge must not cancel or block the page's legitimate network response");
      // The real network response is now complete. A previously started Serwist
      // write can settle independently of the client response; watch that full window.
      await tab.evaluate(async ({localeCache,probe,stale,scopeMarker})=>{
        const deadline=Date.now()+1250;
        do {
          if(await caches.match(probe,{cacheName:localeCache})){
            throw Error("PWA_PURGE_LOCALE_COLLISION: pre-purge fetch repopulated the locale cache");
          }
          await new Promise(resolve=>setTimeout(resolve,20));
        } while(Date.now()<deadline);
        if(await caches.match(stale,{cacheName:localeCache}))throw Error("Stale cached locale survived");
        if(!(await caches.match(stale,{cacheName:scopeMarker})))throw Error("Other cache lost");
        if(sessionStorage.getItem(scopeMarker)!=="keep")throw Error("Session marker lost");
      },{localeCache,probe,stale,scopeMarker});
      assert.deepEqual(await tab.evaluate(probe=>fetch(probe).then(r=>r.json()),probe),
        {marker:"after-purge"});
      await tab.waitForFunction(async ({localeCache,probe})=>{
        const entry=await caches.match(probe,{cacheName:localeCache});
        return (await entry?.json())?.marker==="after-purge";
      },{localeCache,probe});
      assert.equal(networkCalls,2);
      console.log("PWA_PURGE_LOCALE_COLLISION_PASS");
    } finally {
      release.resolve();
      await race.close();
    }
  });
  await check("Legacy maintenance stays guarded and emergency Settings purges only downloaded data", async () => {
    const isolated=await browser.newContext({serviceWorkers:"allow"});
    await isolated.route("**/*", route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    try {
      const first=await isolated.newPage();
      await first.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
      await first.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),null,{timeout:20000});
      const second=await isolated.newPage();
      await second.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
      await second.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),null,{timeout:20000});
      const keys=["efhc-serwist-pages","efhc-serwist-assets",
        "efhc-serwist-locale","efhc-serwist-media"];
      await first.evaluate(async names=>{
        localStorage.setItem("efhc-public-cache-clear-proof","preserved");
        for(const [index,name] of names.entries()){
          const cache=await caches.open(name);
          await cache.put("/efhc/public-cache-clear-proof-"+index+".txt",
            new Response("remove-me"));
        }
        const unrelated=await caches.open("another-application-cache");
        await unrelated.put("/outside-public-cache-proof",new Response("keep-me"));
      },keys);
      // The real button creates user activity, not a six-second idle window.
      await second.evaluate(()=>{
        const field=document.createElement("input");
        field.id="efhc-pwa-active-form-proof";
        document.body.appendChild(field);
        field.focus();
      });
      const requestClear=async()=>first.evaluate(async()=>{
        const active=navigator.serviceWorker.controller;
        if(!active)throw Error("Missing active Serwist worker");
        const channel=new MessageChannel();
        const message=new Promise((resolve,reject)=>{
          const timeout=setTimeout(()=>reject(Error("Runtime purge reply timeout")),9000);
          channel.port1.onmessage=event=>{
            clearTimeout(timeout);channel.port1.close();resolve(event.data);
          };
        });
        active.postMessage({type:"EFHC_PWA_CLEAR_PUBLIC_CACHE"},[channel.port2]);
        return await message;
      });
      const blocked=await requestClear();
      assert.equal(blocked.status,"busy",
        "Active editor in another scoped tab must block manual cleanup");
      await second.evaluate(
        ()=>document.getElementById("efhc-pwa-active-form-proof")?.remove());
      // Immediate manual click must work without waiting for upgrade idleness.
      await first.evaluate(()=>document.dispatchEvent(
        new PointerEvent("pointerdown",{bubbles:true})));
      const cleared=await requestClear();
      if(cleared.status!=="cleared"){
        const remaining=await first.evaluate(async names=>{
          const current=await caches.keys();
          return await Promise.all(names.map(async (name,index)=>({
            name,present:current.includes(name),
            seeded:Boolean(await caches.match(
              "/efhc/public-cache-clear-proof-"+index+".txt",{cacheName:name})),
          })));
        },keys);
        console.log("PWA_LEGACY_CLEAR_DIAGNOSTIC",JSON.stringify({
          status:cleared.status,safe:cleared.safe??null,count:cleared.count??null,remaining,
        }));
      }
      assert.equal(cleared.status,"cleared");
      assert.equal(cleared.count,keys.length,
        "Only the four Serwist runtime buckets should be removed");
      const retention=await first.evaluate(async names=>{
        const remaining=[];
        for(const [index,name] of names.entries()){
          const cache=await caches.open(name);
          remaining.push(Boolean(await cache.match(
            "/efhc/public-cache-clear-proof-"+index+".txt")));
        }
        const foreign=await caches.open("another-application-cache");
        let offlineShell=false;
        for(const name of await caches.keys()){
          if(names.includes(name))continue;
          const cache=await caches.open(name);
          const requests=await cache.keys();
          if(requests.some(request=>
            new URL(request.url).pathname==="/efhc/offline.html"))
            offlineShell=true;
        }
        return {
          remaining,
          foreign:Boolean(await foreign.match("/outside-public-cache-proof")),
          owner:localStorage.getItem("efhc-public-cache-clear-proof"),
          offlineShell,
        };
      },keys);
      assert.deepEqual(retention.remaining,[false,false,false,false]);
      assert.equal(retention.foreign,true,"Other application caches must survive");
      assert.equal(retention.owner,"preserved","Owner data must survive manual purge");
      assert.equal(retention.offlineShell,true,"Serwist offline precache must survive");
      console.log("PWA_SERWIST_PUBLIC_CLEAR_PASS",JSON.stringify({blocked,cleared,retention}));
      // E2E acceptance must click the actual Settings button, not just send
      // a synthetic worker message. The pointer event must not produce busy.
      await first.goto(base+"web-profile/",{waitUntil:"domcontentloaded",timeout:30000});
      const settingsOwner = "0000000042";
      // Seed the same owner before reload and allow the real app to hydrate
      // its normal preferences and a nonempty display snapshot together.
      await first.evaluate(({owner,ownerCacheKey,settingsKey}) => {
        const snapshot = JSON.stringify({owner,entries:[{
          key:["ranks",owner,"emergency-cache-fixture"],
          data:{fixture:"downloaded-display"},updatedAt:Date.now(),
        }]});
        const initialSettings = JSON.stringify({...JSON.parse(sessionStorage.getItem(settingsKey)||"{}"),
          settings_owner:owner,interface_settings_version:4,reduce_motion:false});
        sessionStorage.setItem("efhc:resolved-display-owner",JSON.stringify({global_id:owner,principal:"browser"}));
        sessionStorage.setItem(ownerCacheKey,snapshot);
        localStorage.setItem(ownerCacheKey+":"+owner,snapshot);
        sessionStorage.setItem(settingsKey,initialSettings);
        localStorage.setItem(settingsKey+":"+owner,initialSettings);
      },{owner:settingsOwner,ownerCacheKey,settingsKey});
      await first.reload({waitUntil:"domcontentloaded",timeout:30000});
      await first.locator('[data-profile-settings-entry="interface-card"]')
        .waitFor({state:"visible",timeout:20000});
      const tabs = first.locator("[data-profile-primary-navigation]");
      const tabPaint = await tabs.evaluate((element) => {
        const group = getComputedStyle(element);
        return {
          groupBorder: group.borderTopWidth,
          buttons: Array.from(element.querySelectorAll("button"), (button) => {
            const style = getComputedStyle(button);
            return {border: style.borderTopWidth, color: style.borderTopColor, shadow: style.boxShadow};
          }),
        };
      });
      assert.equal(tabPaint.groupBorder, "0px", "Profile tabs must not have a group frame");
      assert.equal(tabPaint.buttons.length, 4);
      assert.ok(tabPaint.buttons.every(({border}) => border === "1px"),
        "Active and inactive Profile tabs must have the same border thickness");
      assert.equal(tabPaint.buttons[0].shadow, "none", "Active tab must not add an inset stroke");
      assert.notEqual(tabPaint.buttons[0].color, tabPaint.buttons[1].color,
        "Brightness must distinguish the active Profile tab");
      await first.locator('[data-profile-settings-entry="interface-card"]').click();
      const settings = first.locator('[data-modal-reference-layout="settings"]');
      const dismiss = settings.locator(".efhc-modal-close");
      assert.equal((await dismiss.textContent()).trim(), "×");
      assert.ok(await dismiss.getAttribute("aria-label"), "The close icon needs an accessible name");
      const closePaint = await dismiss.evaluate((element) => {
        const style = getComputedStyle(element);
        return {width: style.width, height: style.height, radius: style.borderTopLeftRadius};
      });
      assert.equal(closePaint.width, closePaint.height);
      assert.equal(closePaint.radius, "50%", "Settings close button must be round");
      const settingsHeader = settings.locator('[data-modal-drag-handle="true"]');
      const headerPaint = await settingsHeader.evaluate((element) => {
        const style = getComputedStyle(element);
        return [style.backgroundColor, style.backgroundImage, style.borderBottomWidth];
      });
      assert.deepEqual(headerPaint, ["rgba(0, 0, 0, 0)", "none", "0px"],
        "The Settings heading must have no separate plate or divider");
      const maintenance = first.locator('[data-profile-settings-maintenance="visible"]');
      const clearButton = maintenance.locator('[data-pwa-clear-public-cache="true"]');
      assert.equal(await maintenance.locator("summary").count(), 0,
        "Maintenance must no longer require opening a disclosure");
      assert.equal(await maintenance.getByRole("button").count(), 1,
        "Settings must expose the clear button as its only maintenance control");
      await clearButton.waitFor({state:"visible"});
      assert.equal(await maintenance.getByRole("heading").count(), 0,
        "Do not show an extra maintenance heading");
      await first.evaluate(async()=>{
        const cache=await caches.open("efhc-serwist-pages");
        await cache.put("/efhc/pwa-button-clear-proof.txt",
          new Response("remove-me"));
      });
      // Preserve real SW scope/control while simulating a loaded copy unable
      // to acknowledge the automatic lifecycle safety query.
      const unresponsive = await isolated.newPage();
      try {
        await unresponsive.addInitScript(() => {
          navigator.serviceWorker?.addEventListener("message", event => {
            if (event.data?.type === "EFHC_PWA_CLIENT_SAFE") event.stopImmediatePropagation();
          }, {capture:true});
        });
        await unresponsive.goto(base+"web-profile/",{waitUntil:"domcontentloaded",timeout:30000});
        await unresponsive.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),null,{timeout:20000});
        const reduceMotion = settings.locator('[data-setting="reduce_motion"]');
        await reduceMotion.click();
        const expectedMotion = true;
        await first.waitForFunction(({key,owner,expected}) => {
          const correct = raw => {
            const value=JSON.parse(raw||"null");
            return value?.settings_owner===owner && value.reduce_motion===expected;
          };
          return correct(sessionStorage.getItem(key)) && correct(localStorage.getItem(key+":"+owner));
        },{key:settingsKey,owner:settingsOwner,expected:expectedMotion},{timeout:12000});
        assert.equal(await reduceMotion.getAttribute("aria-pressed"),String(expectedMotion));
        const proof = await first.evaluate(async ({authSessionKey,ownerCacheKey,settingsKey,owner,expectedMotion}) => {
          const read = async () => {
            const runtime = await caches.match("/efhc/pwa-button-clear-proof.txt", {cacheName:"efhc-serwist-pages"});
            const foreign = await caches.match("/outside-public-cache-proof", {cacheName:"another-application-cache"});
            const ownedPageCopies = await Promise.all((await caches.keys()).map(async name => {
              if (!name.includes("precache")) return [];
              return (await (await caches.open(name)).keys()).map(request => new URL(request.url).pathname);
            }));
            return {runtime:Boolean(runtime),foreign:Boolean(foreign),
              offlinePage:ownedPageCopies.flat().includes("/efhc/web-profile/index.html")};
          };
          const initial = await read();
          const resumeKey = "efhc.demo.guest.resume";
          const identityKey = "efhc:resolved-display-owner";
          const durableKey = ownerCacheKey + ":" + owner;
          // Syntactically valid synthetic markers, never issued by any server.
          // Requests to external origins are blocked for this isolated context.
          const credentialMarker = JSON.stringify({
            token_type:"Bearer", access_token:"local_efhc_test_marker_not_a_real_credential",
            expires_at:new Date(Date.now()+600000).toISOString(),
          });
          const resumeMarker = "local_efhc_test_marker_not_a_real_resume";
          const identityMarker = sessionStorage.getItem(identityKey);
          const settingsKept = raw => {
            const value=JSON.parse(raw||"null");
            return value?.settings_owner===owner && value.reduce_motion===expectedMotion;
          };
          initial.downloadedSnapshot=JSON.parse(localStorage.getItem(durableKey)||"null")?.entries?.length>0;
          sessionStorage.setItem(authSessionKey,credentialMarker);
          localStorage.setItem(resumeKey,resumeMarker);
          window.__efhcInspectEmergencyPurge = async () => {
            return {...await read(),samePage:true,
              login:sessionStorage.getItem(authSessionKey)===credentialMarker,
              resume:localStorage.getItem(resumeKey)===resumeMarker,
              identity:JSON.parse(identityMarker||"null")?.global_id===owner &&
                sessionStorage.getItem(identityKey)===identityMarker,
              settings:settingsKept(sessionStorage.getItem(settingsKey)) &&
                settingsKept(localStorage.getItem(settingsKey+":"+owner)),
              downloadedSnapshot:localStorage.getItem(durableKey)!==null ||
                JSON.parse(sessionStorage.getItem(ownerCacheKey)||"null")?.entries?.length>0};
          };
          return initial;
        },{authSessionKey,ownerCacheKey,settingsKey,owner:settingsOwner,expectedMotion});
        assert.deepEqual(proof,{runtime:true,foreign:true,offlinePage:true,downloadedSnapshot:true});
        const before = await first.evaluate(() => performance.timeOrigin);
        await clearButton.click();
        await first.waitForFunction(()=>{
          const text=document.querySelector(
            ".efhc-profile-pwa-maintenance [role=status]")?.textContent || "";
          return /Serwist public runtime cache cleared|^кеш очищен$/i.test(text);
        },null,{timeout:12000});
        assert.equal(await first.evaluate(() => performance.timeOrigin),before,
          "Emergency purge must not reload the app");
        assert.equal(unresponsive.isClosed(),false,
          "Emergency purge must not require closing other app copies");
        assert.deepEqual(await first.evaluate(() => window.__efhcInspectEmergencyPurge()),
          {runtime:false,foreign:true,offlinePage:false,samePage:true,
            login:true,resume:true,identity:true,settings:true,downloadedSnapshot:false},
          "Emergency cleanup deletes only downloaded data and retains access/settings");
        assert.equal(await reduceMotion.getAttribute("aria-pressed"),String(expectedMotion),
          "Emergency purge must preserve the selected live preference");
      } finally { await unresponsive.close(); }
      const buttonCleared=await first.evaluate(async()=>!(
        await (await caches.open("efhc-serwist-pages"))
          .match("/efhc/pwa-button-clear-proof.txt")));
      assert.equal(buttonCleared,true,"Actual Settings cache button did not clear runtime data");
      await dismiss.click();
      await settings.waitFor({state:"hidden"});
      await first.close();
      await second.close();
      const reopened = await isolated.newPage();
      await reopened.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
      await reopened.waitForFunction(async build => {
        if (document.querySelector('meta[name="efhc-build-id"]')?.content !== build) return false;
        for (const name of await caches.keys()) {
          if (!name.includes("precache")) continue;
          const entries = await (await caches.open(name)).keys();
          if (entries.some(request => new URL(request.url).pathname === "/efhc/web-profile/index.html")) return true;
        }
        return false;
      },exportConfig.build_id,{timeout:30000});
      console.log("PWA_SERWIST_SETTINGS_BUTTON_PASS");

    } finally { await isolated.close(); }
  });
  await check("Profile language surfaces match in ten themes and account actions use approved copy", async () => {
    const isolated = await browser.newContext({serviceWorkers:"allow", viewport:{width:390,height:900}});
    try {
      const profile = await isolated.newPage();
      await profile.goto(base+"web-profile/",{waitUntil:"domcontentloaded",timeout:30000});
      for (let i=1;i<=10;i++){
        const ct = "CT-"+String(i).padStart(2,"0");
        await profile.evaluate(({key,ct}) => {
          const current = JSON.parse(sessionStorage.getItem(key)||"null") || {};
          Object.assign(current, {interface_settings_version:4,lang:"ru",color_theme_id:ct,global_theme_id:ct.slice(3)});
          sessionStorage.setItem(key,JSON.stringify(current));
        },{key:settingsKey,ct});
        await profile.reload({waitUntil:"domcontentloaded",timeout:20000});
        await profile.locator('#profilePage').waitFor({state:"visible",timeout:12000});
        await profile.locator(`[data-theme-page-surface="true"][data-color-theme-id="${ct}"]`).first().waitFor({state:"attached",timeout:10000});
        const trigger = profile.locator('#profilePage .source-profile-language-button');
        const menu = profile.locator('#profilePage .source-profile-language-menu');
        const paint = (locator) => locator.evaluate(el => {
          const css = getComputedStyle(el); return [css.backgroundColor, css.backgroundImage];
        });
        const closed = await paint(trigger);
        await trigger.click();
        await menu.waitFor({state:"visible"});
        assert.deepEqual(await paint(menu), closed, ct+" closed and expanded Profile language surfaces");
        assert.notEqual(closed[0], "rgba(0, 0, 0, 0)", ct+" language surface must have a fill");
        assert.equal(await menu.getByRole("option").count(),16);
      }
      const trigger = profile.locator('#profilePage .source-profile-language-button');
      await trigger.click();
      await profile.locator('[data-profile-settings-entry="interface-card"]').click();
      const settings = profile.locator('[data-modal-reference-layout="settings"]');
      const maintenance = settings.locator('[data-profile-settings-maintenance="visible"]');
      await maintenance.getByText("Очистить кеш", {exact:true}).waitFor({state:"visible"});
      await maintenance.getByRole("button", {name:"Очистить",exact:true}).waitFor({state:"visible"});
      await settings.locator(".efhc-modal-close").click();
      await settings.waitFor({state:"hidden"});
      await profile.locator('[data-provider-entry="profile-footer"]').click();
      const providers = profile.locator('[data-provider-route="account-providers"]');
      await providers.waitFor({state:"visible"});
      assert.equal(await providers.locator(".efhc-account-provider-card").count(),2);
      assert.equal(await providers.getByRole("button",{name:"Подключить",exact:true}).count(),2);
      assert.equal(await providers.getByText("Открыть вход через Telegram",{exact:true}).count(),0);
      const frames = await providers.locator(".efhc-account-provider-card").evaluateAll(cards =>
        cards.map(card=>getComputedStyle(card).borderTopWidth));
      assert.deepEqual(frames, ["1px","1px"], "Provider card frames must be preserved");
      const statusFills = await providers.locator("[data-provider-state]").evaluateAll(nodes =>
        nodes.map(node=>getComputedStyle(node).backgroundColor));
      assert.ok(statusFills.length===2 && statusFills.every(fill=>fill==="rgba(0, 0, 0, 0)"),
        "Provider status text has no separate fill");
      const plates = await providers.locator("[data-provider-row]").evaluateAll(rows =>
        rows.map(row => {
          const style = getComputedStyle(row);
          return [style.backgroundColor, style.backgroundImage, style.boxShadow, style.borderTopWidth];
        }));
      assert.deepEqual(plates, Array(2).fill(["rgba(0, 0, 0, 0)", "none", "none", "0px"]),
        "Provider rows must have no inner plates while the outer cards retain their frames");
      console.log("PROFILE_LANGUAGE_AND_ACCOUNT_VISUAL_PASS");
    } finally { await isolated.close(); }
  });
  await check("Serwist A to B atomically swaps critical HTML JS CSS at safe idle", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const workerFile=path.join(root,"sw.js");
    const configFile=path.join(root,"pwa-build.json");
    const originalWorker=await readFile(workerFile,"utf8");
    const originalConfig=await readFile(configFile,"utf8");
    const oldBuildId=JSON.parse(originalConfig).build_id;
    const oldHtml=JSON.parse(originalConfig).precache.filter(url=>url.endsWith(".html"));
    const originals=new Map();
    const newScript="_next/static/efhc-upgrade-staged.js";
    const newCss="_next/static/efhc-upgrade-staged.css";
    const thirdScript="_next/static/efhc-upgrade-third.js";
    const thirdCss="_next/static/efhc-upgrade-third.css";
    const thirdScriptUrl="/efhc/"+thirdScript;
    const thirdCssUrl="/efhc/"+thirdCss;
    const scriptUrl="/efhc/"+newScript;
    const cssUrl="/efhc/"+newCss;
    try {
      for (const url of oldHtml) {
        const filepath=path.join(root,url.slice("/efhc/".length));
        originals.set(filepath,await readFile(filepath,"utf8"));
      }
      await writeFile(path.join(root,newScript),"window.__EFHC_NEW_PWA_ASSET__=true;","utf8");
      await writeFile(path.join(root,newCss),":root{--efhc-upgrade-css-proof:updated}","utf8");
      const rootHtmlPath=path.join(root,"index.html");
      const index=await readFile(rootHtmlPath,"utf8");
      assert.ok(index.includes("</head>"),"Next landing HTML missing head");
      await writeFile(rootHtmlPath,index.replace("</head>",
        `<link rel="stylesheet" href="${cssUrl}"><script defer src="${scriptUrl}"></script></head>`),"utf8");
      // Regenerate the actual release, including new build markers and
      // Serwist's revisioned critical manifest; never text-patch worker JS.
      const {spawnSync}=await import("node:child_process");
      const regenerate=spawnSync("python3",[
        "site/ci/pages-tools/fix_pages_assets.py",
        "--directory",root,"--base-path","/efhc",
      ],{encoding:"utf8",env:process.env});
      assert.equal(regenerate.status,0,
        "Second Serwist export failed: "+regenerate.stderr+"\n"+regenerate.stdout);
      const nextConfig=JSON.parse(await readFile(configFile,"utf8"));
      const newBuildId=nextConfig.build_id;
      assert.notEqual(newBuildId,oldBuildId,"second actual export did not change build");
      assert.ok(nextConfig.precache_critical.includes(scriptUrl));
      assert.ok(nextConfig.precache_critical.includes(cssUrl));
      await page.evaluate(() => window.dispatchEvent(new Event("online")));
      await page.waitForFunction(id=>
        document.querySelector('meta[name="efhc-build-id"]')?.content===id &&
        window.__EFHC_NEW_PWA_ASSET__===true,
      newBuildId,{timeout:65000});
      const view=await page.evaluate(async () => ({
        build:document.querySelector('meta[name="efhc-build-id"]')?.content,
        asset:Boolean(window.__EFHC_NEW_PWA_ASSET__),
        css:getComputedStyle(document.documentElement)
          .getPropertyValue("--efhc-upgrade-css-proof").trim(),
        react:Boolean(document.querySelector("#__next")),
        active:(await navigator.serviceWorker.getRegistration())?.active?.state,
        controlled:Boolean(navigator.serviceWorker.controller),
      }));
      assert.equal(view.build,newBuildId,"new HTML build marker did not activate");
      assert.equal(view.asset,true,"successor JS did not run");
      assert.equal(view.css,"updated","successor CSS did not apply");
      assert.equal(view.react,true,"the active React UI vanished");
      assert.equal(view.active,"activated");
      assert.equal(view.controlled,true);
      console.log("PWA_SERWIST_REAL_BUILD_TRANSITION",JSON.stringify(view));
      const successor=await context.newPage();
      try {
        await context.setOffline(true);
        await successor.goto(base,{waitUntil:"domcontentloaded",timeout:25000});
        const offline=await successor.evaluate(() => ({
          build:document.querySelector('meta[name="efhc-build-id"]')?.content,
          js:Boolean(window.__EFHC_NEW_PWA_ASSET__),
          css:getComputedStyle(document.documentElement)
            .getPropertyValue("--efhc-upgrade-css-proof").trim(),
          react:Boolean(document.querySelector("#__next")),
        }));
        assert.deepEqual(offline,{build:newBuildId,js:true,css:"updated",react:true},
          "Offline successor mixed older and newer HTML/JS/CSS");
        console.log("PWA_SERWIST_OFFLINE_SUCCESSOR",JSON.stringify(offline));
      }finally{
        await context.setOffline(false);
        await successor.close();
      }

      // Generate a THIRD real release. B's dynamic JS/CSS are no longer on
      // the HTTP server; a stale B tab must still be able to fetch them from
      // Serwist's protected legacy cache until safe retirement.
      await writeFile(path.join(root,thirdScript),
        "window.__EFHC_THIRD_PWA_ASSET__=true;","utf8");
      await writeFile(path.join(root,thirdCss),
        ":root{--efhc-upgrade-css-proof:third}","utf8");
      const secondIndex=await readFile(rootHtmlPath,"utf8");
      assert.ok(secondIndex.includes(scriptUrl)&&secondIndex.includes(cssUrl),
        "B index missing the staged version assets");
      await writeFile(rootHtmlPath,
        secondIndex.replace(scriptUrl,thirdScriptUrl).replace(cssUrl,thirdCssUrl),"utf8");
      await Promise.all([
        unlink(path.join(root,newScript)),
        unlink(path.join(root,newCss)),
      ]);
      const thirdRegenerate=spawnSync("python3",[
        "site/ci/pages-tools/fix_pages_assets.py",
        "--directory",root,"--base-path","/efhc",
      ],{encoding:"utf8",env:process.env});
      assert.equal(thirdRegenerate.status,0,
        "Third Serwist export failed: "+thirdRegenerate.stderr+"\n"+thirdRegenerate.stdout);
      const thirdConfig=JSON.parse(await readFile(configFile,"utf8"));
      const thirdBuildId=thirdConfig.build_id;
      assert.notEqual(thirdBuildId,newBuildId,"C must differ from B");
      assert.ok(thirdConfig.precache_critical.includes(thirdScriptUrl));
      assert.ok(thirdConfig.precache_critical.includes(thirdCssUrl));
      assert.ok(!thirdConfig.precache.includes(scriptUrl),
        "B's removed JS must not be in the new release manifest");
      await page.evaluate(async () => {
        const reg=await navigator.serviceWorker.getRegistration();
        if(!reg)throw Error("No B registration before C");
        await reg.update();
      });
      await page.waitForFunction(id=>
        document.querySelector('meta[name="efhc-build-id"]')?.content===id &&
        window.__EFHC_THIRD_PWA_ASSET__===true,
      thirdBuildId,{timeout:65000});
      const cLive=await page.evaluate(()=>({
        build:document.querySelector('meta[name="efhc-build-id"]')?.content,
        third:Boolean(window.__EFHC_THIRD_PWA_ASSET__),
        css:getComputedStyle(document.documentElement)
          .getPropertyValue("--efhc-upgrade-css-proof").trim(),
        react:Boolean(document.querySelector("#__next")),
      }));
      assert.deepEqual(cLive,{build:thirdBuildId,third:true,css:"third",react:true},
        "A→B→C did not activate a coherent third HTML/JS/CSS release");
      const thirdTab=await context.newPage();
      try {
        await context.setOffline(true);
        await thirdTab.goto(base,{waitUntil:"domcontentloaded",timeout:25000});
        const cOffline=await thirdTab.evaluate(() => ({
          build:document.querySelector('meta[name="efhc-build-id"]')?.content,
          third:Boolean(window.__EFHC_THIRD_PWA_ASSET__),
          css:getComputedStyle(document.documentElement)
            .getPropertyValue("--efhc-upgrade-css-proof").trim(),
          react:Boolean(document.querySelector("#__next")),
        }));
        assert.deepEqual(cOffline,{build:thirdBuildId,third:true,css:"third",react:true},
          "Offline A→B→C reopened mixed builds");
        // Native Serwist handles its own precache generations; the compatibility
        // contract for pre-Serwist open tabs is tested separately below.
        console.log("PWA_SERWIST_A_B_C_OFFLINE",JSON.stringify(cOffline));
      } finally {
        await context.setOffline(false);
        await thirdTab.close();
      }

      // A genuine pre-Serwist cache may exist in an old installed browser.
      // Do not serve a removed JS file from that cache after HTTP 404:
      // only the predecessor may use its own resources before handoff.
      // Serwist retires proven EFHC legacy buckets ONCE on native activation.
      const oldLegacy="efhc-pwa-test-prior-static";
      const oldRuntime="efhc-public-pages-test-prior";
      const oldStatic="efhc-static-assets-test-prior";
      const oldMedia="efhc-public-media";
      const oldLocale="efhc-public-translations";
      const unrelated="efhc-unrelated-app-test";
      const oldUrl=new URL("/efhc/_next/static/efhc-old-retired.js",origin).href;
      const stale=await context.newPage();
      const workerBeforeMigration=await readFile(workerFile,"utf8");
      const workerTimes=await stat(workerFile);
      try {
        await boundedSerwistPhase("legacy.stale.goto",()=>
          stale.goto(base+"offline.html",{waitUntil:"domcontentloaded",timeout:15000}),19000);
        await boundedSerwistPhase("legacy.seed",()=>page.evaluate(async ({oldLegacy,oldRuntime,oldStatic,oldMedia,oldLocale,unrelated,oldUrl})=>{
          const store=async (name,url,value)=>{
            const cache=await caches.open(name);
            await cache.put(url,new Response(value,{status:200}));
          };
          await store(oldLegacy,oldUrl,"legacy-old");
          await store(oldRuntime,new URL("/efhc/old-page/index.html",location.origin).href,"old-page");
          await store(oldStatic,new URL("/efhc/old-file.css",location.origin).href,"old-css");
          await store(oldMedia,new URL("/efhc/assets/efhc/legacy-cover.webp",location.origin).href,"old-media");
          await store(oldLocale,new URL("/efhc/locale/en.json",location.origin).href,"old-locale");
          await store(unrelated,new URL("/other-app/data.txt",location.origin).href,"other-app");
        },{oldLegacy,oldRuntime,oldStatic,oldMedia,oldLocale,unrelated,oldUrl}),15000);
        const onlineLegacy=await boundedSerwistPhase("legacy.fetch.no-fallback",()=>
          stale.evaluate(async url=>{
            const response=await fetch(url);
            return {status:response.status,content:await response.text()};
          },oldUrl),15000);
        assert.notEqual(onlineLegacy.content,"legacy-old",
          "A new Serwist worker must not serve obsolete JS from retired EFHC cache");
        const seeded=await page.evaluate(async names=>{
          const list=await caches.keys();
          return names.every(name=>list.includes(name));
        },[oldLegacy,oldRuntime,oldStatic,oldMedia,oldLocale]);
        assert.equal(seeded,true,"Legacy evidence must exist before native activation");
        // Change only the worker bytes: the same complete Serwist build stays
        // valid and a real waiting successor observes the old scoped tab.
        await writeFile(workerFile,
          workerBeforeMigration+"\n// native legacy retirement fixture\n","utf8");
        await utimes(workerFile,new Date(),new Date(Date.now()+5000));
        await page.evaluate(async()=>{
          const reg=await navigator.serviceWorker.getRegistration();
          if(!reg)throw Error("Missing active Serwist before legacy retirement");
          await reg.update();
        });
        await page.waitForFunction(async()=>{
          const reg=await navigator.serviceWorker.getRegistration();
          return Boolean(reg?.waiting?.state==="installed");
        },null,{timeout:18000});
        await page.waitForTimeout(1200);
        const stillWaiting=await page.evaluate(async()=>
          (await navigator.serviceWorker.getRegistration())?.waiting?.state);
        assert.equal(stillWaiting,"installed",
          "Unresponsive old tab must block a premature generation handoff");
        await stale.goto("about:blank",{waitUntil:"domcontentloaded",timeout:12000});
        await stale.waitForURL("about:blank",{waitUntil:"domcontentloaded",timeout:12000});
        await page.waitForFunction(async()=>{
          const reg=await navigator.serviceWorker.getRegistration();
          return Boolean(reg?.active?.state==="activated" && !reg.waiting);
        },null,{timeout:30000});
        await page.waitForFunction(async names=>{
          const list=await caches.keys();
          return names.every(name=>!list.includes(name));
        },[oldLegacy,oldRuntime,oldStatic,oldMedia,oldLocale],{timeout:18000});
        const kept=await page.evaluate(async name=>({
          names:await caches.keys(),
          unrelated:Boolean(await (await caches.open(name))
            .match(new URL("/other-app/data.txt",location.origin).href)),
        }),unrelated);
        assert.ok(kept.names.includes(unrelated) && kept.unrelated,
          "Native legacy migration must not delete unrelated caches");
        console.log("PWA_SERWIST_LEGACY_SAFE_RETIREMENT",JSON.stringify({
          removed:5,unsafeTabBlocked:true,otherScopePreserved:true,
        }));
        await page.evaluate(name=>caches.delete(name),unrelated);
      }finally {
        await writeFile(workerFile,workerBeforeMigration,"utf8");
        await utimes(workerFile,workerTimes.atime,workerTimes.mtime);
        await stale.close().catch(()=>undefined);
      }
    }finally{
      await writeFile(workerFile,originalWorker,"utf8");
      await writeFile(configFile,originalConfig,"utf8");
      for(const [file,html] of originals)await writeFile(file,html,"utf8");
      await Promise.all([
        unlink(path.join(root,newScript)).catch(()=>undefined),
        unlink(path.join(root,newCss)).catch(()=>undefined),
        unlink(path.join(root,thirdScript)).catch(()=>undefined),
        unlink(path.join(root,thirdCss)).catch(()=>undefined),
      ]);
    }
  });
  await check("Serwist refuses unsafe native activation while older scoped clients exist", async () => {
    const workerPath=path.join(root,"sw.js");
    const originalWorker=await readFile(workerPath,"utf8");
    const originalTimes=await stat(workerPath);
    const isolated=await browser.newContext({serviceWorkers:"allow"});
    try {
      const first=await isolated.newPage();
      await first.goto(base+"offline.html",{waitUntil:"domcontentloaded",timeout:18000});
      await first.evaluate(async scope=>{
        await navigator.serviceWorker.register(scope+"sw.js",{scope,updateViaCache:"none"});
        await navigator.serviceWorker.ready;
      },base);
      await first.reload({waitUntil:"domcontentloaded",timeout:18000});
      await first.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),null,{timeout:12000});
      const second=await isolated.newPage();
      await second.goto(base+"offline.html",{waitUntil:"domcontentloaded",timeout:18000});
      await second.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),null,{timeout:12000});
      // A byte-level SW update with the same valid Serwist manifest isolates
      // the native message protocol; no fake service worker replaces Serwist.
      await writeFile(workerPath,originalWorker+"\n// guarded message protocol browser proof\n");
      await utimes(workerPath,new Date(),new Date(Date.now()+5000));
      await first.evaluate(async scope=>{
        const reg=await navigator.serviceWorker.getRegistration(scope);
        if(!reg)throw Error("Expected first Serwist registration");
        await reg.update();
      },base);
      // Unsupported offline/legacy pages cannot approve automatic activation.
      const blocked = await boundedSerwistPhase("message.guard.waiting",()=>
        first.evaluate(async scope=>{
          const deadline=Date.now()+18000;
          while(Date.now()<deadline){
            const reg=await navigator.serviceWorker.getRegistration(scope);
            if(reg?.waiting?.state==="installed" && !reg.installing){
              const channel=new MessageChannel();
              const answer=new Promise((resolve,reject)=>{
                const timer=setTimeout(()=>reject(Error("Safety vote timeout")),7000);
                channel.port1.onmessage=event=>{
                  clearTimeout(timer);channel.port1.close();resolve(event.data);
                };
              });
              reg.waiting.postMessage({type:"EFHC_PWA_CHECK_CLIENTS"},[channel.port2]);
              return {waiting:reg.waiting.state,answer:await answer};
            }
            await new Promise(resolve=>setTimeout(resolve,75));
          }
          throw Error("No waiting Serwist worker found");
        },base),26000);
      assert.equal(blocked.waiting,"installed");
      assert.equal(blocked.answer.safe,false,
        "An unsupported legacy tab must block forced activation");
      await first.waitForTimeout(500);
      assert.equal(await first.evaluate(async scope=>
        (await navigator.serviceWorker.getRegistration(scope))?.waiting?.state,
        base),"installed","Unsafe old client was replaced unexpectedly");
      await Promise.all([
        first.goto("about:blank",{waitUntil:"domcontentloaded",timeout:12000}),
        second.goto("about:blank",{waitUntil:"domcontentloaded",timeout:12000}),
      ]);
      const successor=await isolated.newPage();
      await successor.goto(base+"offline.html",{waitUntil:"domcontentloaded",timeout:18000});
      await successor.waitForFunction(async scope=>{
        const reg=await navigator.serviceWorker.getRegistration(scope);
        return Boolean(reg?.active?.state==="activated" && !reg.waiting);
      },base,{timeout:18000});
      console.log("PWA_SERWIST_SAFE_MESSAGE_GATE_PASS",JSON.stringify(blocked));
    } finally {
      await writeFile(workerPath,originalWorker,"utf8");
      // Do not poison the next interrupted-update test: preserve this
      // fixture's original HTTP Last-Modified rather than a future timestamp.
      await utimes(workerPath,originalTimes.atime,originalTimes.mtime);
      await boundedSerwistPhase("message.guard.context.close",()=>isolated.close(),15000);
    }
  });
  await check("Serwist failed critical update retains the previously installed offline worker",async()=>{
    const missingUrl=exportConfig.precache_critical.find(url=>
      url.endsWith("/offline-readonly.html"));
    assert.ok(missingUrl,"Critical offline fallback must be in the Serwist install manifest");
    const missingPath=path.join(root,missingUrl.slice("/efhc/".length));
    const workerPath=path.join(root,"sw.js");
    const originalCritical=await readFile(missingPath);
    const originalWorker=await readFile(workerPath,"utf8");
    const isolated=await browser.newContext({serviceWorkers:"allow"});
    try {
      const tab=await isolated.newPage();
      await boundedSerwistPhase("interrupt.install.baseline",()=>
        tab.goto(base+"offline.html",{waitUntil:"domcontentloaded",timeout:15000}),19000);
      const installed=await boundedSerwistPhase("interrupt.worker.install",()=>tab.evaluate(async appBase=>{
        const reg=await navigator.serviceWorker.register(appBase+"sw.js",{
          scope:appBase,updateViaCache:"none",
        });
        const active=await Promise.race([
          navigator.serviceWorker.ready.then(r=>r.active),
          new Promise((_,reject)=>setTimeout(()=>
            reject(Error("Original Serwist install timeout")),30000)),
        ]);
        return Boolean(active&&reg.active);
      },base),35000);
      assert.equal(installed,true,"Predecessor must be active before interrupted update");
      // Revision-aware precaching may reuse an unchanged critical entry even
      // if its original file disappears. Change the actual compiled critical
      // manifest URL so the successor MUST fetch a missing dependency; only
      // modifying the worker's trailing comment does not prove install failure.
      const unavailableUrl=missingUrl.replace(
        /offline-readonly\.html$/,"offline-unavailable-critical.html");
      assert.notEqual(unavailableUrl,missingUrl);
      assert.ok(originalWorker.includes(missingUrl),
        "The real Serwist worker must contain the critical manifest URL");
      const incompleteWorker=originalWorker.replaceAll(missingUrl,unavailableUrl)+
        "\n/* synthetic incomplete successor, not a release */\n";
      // Python's local static server exposes Last-Modified with one-second
      // precision. An immediate rewrite can appear unchanged to the browser
      // update fetch (HTTP 304), never triggering the negative install.
      // Give the deliberately broken, TEST-ONLY successor a distinct mtime.
      const originalHttp=await tab.request.get(base+"sw.js",{
        headers:{"Cache-Control":"no-cache"},
      });
      const previousModified=originalHttp.headers()["last-modified"];
      await writeFile(workerPath,incompleteWorker,"utf8");
      await utimes(workerPath,new Date(),new Date(Date.now()+5000));
      await unlink(missingPath);
      const served=await tab.request.get(base+"sw.js",{
        headers:{"Cache-Control":"no-cache"},
      });
      assert.equal(served.ok(),true,"Updated worker must be served from local export");
      assert.ok((await served.text()).includes(unavailableUrl),
        "The browser must be offered the intentionally broken critical manifest");
      const currentModified=served.headers()["last-modified"];
      assert.ok(currentModified && previousModified &&
        currentModified!==previousModified,
        "A new worker must have a distinct HTTP Last-Modified for the real update test");
      console.log("PWA_SERWIST_INTERRUPT_SCRIPT_HTTP",JSON.stringify({
        previousModified,currentModified,
      }));
      const observed={workers:[],criticalRequests:[],criticalResponses:[]};
      isolated.on("serviceworker",worker=>observed.workers.push(worker.url()));
      isolated.on("request",request=>{
        if(request.url().includes("offline-unavailable-critical.html")) {
          observed.criticalRequests.push(request.url());
        }
      });
      isolated.on("response",response=>{
        if(response.url().includes("offline-unavailable-critical.html")) {
          observed.criticalResponses.push({url:response.url(),status:response.status()});
        }
      });
      const verdict=await boundedSerwistPhase("interrupt.worker.update",()=>tab.evaluate(async appBase=>{
        const reg=await navigator.serviceWorker.getRegistration(appBase);
        if(!reg?.active) throw Error("Predecessor not registered");
        const predecessor=reg.active;
        const events=[];
        return await new Promise(resolve=>{
          let finished=false;
          const complete=result=>{
            if(finished)return;
            finished=true;
            clearTimeout(timeout);
            reg.removeEventListener("updatefound",onNew);
            resolve({result,events,oldStillActive:reg.active===predecessor,
              activeState:reg.active?.state||null,
              installingState:reg.installing?.state||null,
              waitingState:reg.waiting?.state||null,
              controllerState:navigator.serviceWorker.controller?.state||null});
          };
          const onNew=()=>{
            const next=reg.installing;
            events.push("observed-installing:"+(next?.state||"none"));
            if(!next)return;
            const onState=()=>{
              events.push("installing-state:"+next.state);
              if(next.state==="redundant")complete("rejected");
              else if(next.state==="activated")complete("unexpected_activation");
            };
            next.addEventListener("statechange",onState);
            onState();
          };
          const timeout=setTimeout(()=>complete("timeout"),20000);
          reg.addEventListener("updatefound",onNew);
          events.push("update-called");
          void reg.update().then(
            ()=>{events.push("update-resolved");onNew();},
            error=>{events.push("update-rejected:"+String(error));complete("rejected");}
          );
          onNew();
        });
      },base),28000);
      console.log("PWA_SERWIST_INTERRUPT_DIAGNOSTIC",JSON.stringify({verdict,observed}));
      assert.equal(verdict.result,"rejected",
        "Serwist must reject a new worker whose critical file is missing");
      assert.equal(verdict.oldStillActive,true,
        "Failed successor must not replace the previously active worker");
      assert.equal(verdict.activeState,"activated");
      assert.equal(verdict.waitingState,null);
      await isolated.setOffline(true);
      const offline=await verifyOfflineSplashReload(tab,"interrupt.predecessor.offline");
      console.log("PWA_SERWIST_INTERRUPTED_INSTALL_SAFE",
        JSON.stringify({verdict,offline}));
    }finally{
      await Promise.all([
        writeFile(workerPath,originalWorker,"utf8"),
        writeFile(missingPath,originalCritical),
      ]);
      await boundedSerwistPhase("interrupt.context.close",()=>isolated.close(),11000);
    }
  });
  await check("Serwist keeps the installed offline shell when Chromium media cache quota is exhausted",async()=>{
    // Dedicated browser profile and real CDP quota: no synthetic quota-success
    // flag, no changes to the main page or user-scoped browser storage.
    const quotaFile=path.join(root,"quota-overflow.webp");
    const isolated=await browser.newContext({serviceWorkers:"allow"});
    let protocol;
    try {
      await writeFile(quotaFile,Buffer.alloc(5*1024*1024,0x52));
      const tab=await isolated.newPage();
      await boundedSerwistPhase("quota.baseline.goto",()=>
        tab.goto(base+"offline.html",{waitUntil:"domcontentloaded",timeout:18000}),22000);
      await boundedSerwistPhase("quota.worker.ready",()=>tab.evaluate(async appBase=>{
        await navigator.serviceWorker.register(appBase+"sw.js",{
          scope:appBase,updateViaCache:"none",
        });
        return await Promise.race([
          navigator.serviceWorker.ready.then(reg=>Boolean(reg.active)),
          new Promise((_,reject)=>setTimeout(()=>
            reject(Error("Quota baseline Serwist install timeout")),30000)),
        ]);
      },base),35000);
      await tab.waitForFunction(()=>Boolean(navigator.serviceWorker.controller),
        null,{timeout:12000});
      protocol=await isolated.newCDPSession(tab);
      const before=await protocol.send("Storage.getUsageAndQuota",{origin});
      assert.ok(Number.isFinite(before.usage)&&before.usage>=0,
        "Actual Chromium storage usage is required for the quota test");
      const limit=Math.ceil(before.usage+256*1024);
      await protocol.send("Storage.overrideQuotaForOrigin",{origin,quotaSize:limit});
      const constrained=await protocol.send("Storage.getUsageAndQuota",{origin});
      assert.equal(constrained.overrideActive,true,
        "Chromium must confirm that a real quota override is active");
      assert.ok(constrained.quota < 5*1024*1024+before.usage,
        "The new media payload must exceed the constrained storage budget");
      const media=await boundedSerwistPhase("quota.media.fetch",()=>tab.evaluate(
        async url=>{
          try {
            const response=await fetch(url,{cache:"no-store"});
            const body=await response.arrayBuffer();
            return {ok:response.ok,status:response.status,bytes:body.byteLength};
          } catch(error) {
            return {ok:false,status:null,error:String(error)};
          }
        },base+"quota-overflow.webp"),20000);
      assert.equal(media.bytes,5*1024*1024,
        "The entire quota-overflow media response must be consumed before disabling network");
      const state=await tab.evaluate(async url=>{
        const names=await caches.keys();
        const cached=[];
        for(const name of names) {
          if(await (await caches.open(name)).match(url))cached.push(name);
        }
        return {names,mediaCachedIn:cached};
      },base+"quota-overflow.webp");
      const precache=await tab.evaluate(async()=>{
        const names=await caches.keys();
        const details=[];
        for(const name of names) {
          const cached=await caches.open(name);
          const urls=(await cached.keys()).map(request=>new URL(request.url).pathname);
          details.push({name,count:urls.length,
            offlineHtml:urls.includes("/efhc/offline.html"),
            offlineReadonly:urls.includes("/efhc/offline-readonly.html")});
        }
        const registration=await navigator.serviceWorker.getRegistration();
        return {controller:Boolean(navigator.serviceWorker.controller),
          activeState:registration?.active?.state||null,details};
      });
      console.log("PWA_SERWIST_QUOTA_BEFORE_OFFLINE",JSON.stringify({
        before:{usage:before.usage,quota:before.quota},
        constrained:{usage:constrained.usage,quota:constrained.quota,
          overrideActive:constrained.overrideActive},
        media,state,precache,
      }));
      await isolated.setOffline(true);
      const offline=await verifyOfflineSplashReload(tab,"quota.predecessor.offline");
      console.log("PWA_SERWIST_QUOTA_DIAGNOSTIC",JSON.stringify({
        before:{usage:before.usage,quota:before.quota},
        constrained:{usage:constrained.usage,quota:constrained.quota,
          overrideActive:constrained.overrideActive},
        media,state,precache,offline,
      }));
      assert.equal(media.ok,true,
        "Runtime public media must remain accessible online when caching exceeds quota");
      assert.equal(state.mediaCachedIn.length,0,
        "Oversized media must not be retained beyond the measured quota");
    } finally {
      if(protocol) {
        await protocol.send("Storage.overrideQuotaForOrigin",{origin})
          .catch(()=>undefined);
        await protocol.detach().catch(()=>undefined);
      }
      await isolated.setOffline(false).catch(()=>undefined);
      await isolated.close().catch(()=>undefined);
      await unlink(quotaFile).catch(()=>undefined);
    }
  });
  assert.deepEqual(errors,[],"unhandled page errors");
} finally {
  await context.setOffline(false).catch(()=>undefined);
  await writeFile(path.join(artifactDir,"pwa-cache-integration.json"),JSON.stringify({
    base,results,errors,build:"ephemeral",physicalPagesDeploy:false,telegramWebView:"NOT_RUN",vps:"NOT_RUN",
  },null,2));
  await context.unrouteAll({behavior:"ignoreErrors"}).catch(()=>undefined);
  await browser.close();
}
