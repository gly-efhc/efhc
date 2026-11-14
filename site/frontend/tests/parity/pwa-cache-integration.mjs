/** Browser integration against the real Next static export and actual Chromium SW.
 * This is an ephemeral local Pages test; never publish, touch production,
 * prime financial data or grant Admin privileges.
 */
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir, unlink } from "node:fs/promises";
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
const check = async (name,fn) => {
  await fn();
  results.push({name,status:"PASS"});
  console.log("PWA_INTEGRATION_PASS "+name);
};
try {
  await check("Workbox installs critical shell then resumes every required offline page in background", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const config = await (await page.request.get(base+"pwa-build.json")).json();
    assert.equal(config.static_export,true);
    assert.ok(config.precache.length > 40,"real export required");
    assert.ok(config.precache_critical.length > 4,"Workbox critical shell missing");
    assert.ok(config.precache_deferred.length > 0,"deferred export missing");
    await page.evaluate(() => Promise.race([
      navigator.serviceWorker.ready.then(() => true),
      new Promise((_,reject) => setTimeout(() => reject(Error("Workbox install timeout")),95000)),
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
    assert.deepEqual(criticalState.missing,[],"Workbox must atomically cache critical shell before activation");
    assert.ok(criticalState.keys.some(name=>name.includes("precache")),
      "Workbox precache container missing");
    await page.evaluate(async () => {
      const config = await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
      await new Promise((resolve,reject) => {
        const timer=setTimeout(()=>{navigator.serviceWorker.removeEventListener("message",onMessage);
          reject(Error("Workbox deferred queue did not finish"));},95000);
        function onMessage(event) {
          const data=event.data||{};
          if(data.type==="CACHE_COMPLETE"&&data.reason==="deferred"){
            clearTimeout(timer);
            navigator.serviceWorker.removeEventListener("message",onMessage);
            if(data.failed)reject(Error("Workbox deferred resources failed: "+data.failed));
            else resolve(true);
          }
        }
        navigator.serviceWorker.addEventListener("message",onMessage);
        navigator.serviceWorker.controller.postMessage({
          type:"PREFETCH_PRIORITY",urls:config.precache_deferred,
        });
      });
    });
    const info = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      const cfg = await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
      const cached = new Set();
      for (const name of await caches.keys()) {
        for (const req of await (await caches.open(name)).keys()) cached.add(new URL(req.url).pathname);
      }
      const required = cfg.precache.filter(url=>!url.endsWith(".mp3"));
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
    results.push({name:"workbox_offline_inventory",status:"INFO",count:info.cachedCount});
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
        for (const name of cachesList.filter(name => name.endsWith("-static"))) {
          const cache = await caches.open(name);
          if (await cache.match(cssPath)) cached = true;
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
  await check("PWA staged update activates automatically without dropping the running app", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const workerFile = path.join(root,"sw.js");
    const original = await readFile(workerFile,"utf8");
    const originalController = await page.evaluate(() => {
      window.__EFHC_PWA_EVENTS__ = [];
      navigator.serviceWorker.addEventListener("message", event => {
        const data = event.data || {};
        if (["CACHE_FAILED", "CACHE_COMPLETE", "UPDATE_ACTIVATED", "UPDATE_AVAILABLE", "TEST_SKIP_MESSAGE", "CACHE_RETIREMENT_PENDING"].includes(data.type)) {
          window.__EFHC_PWA_EVENTS__.push({type:data.type, failed:data.failed, failedUrls:data.failedUrls, reason:data.reason, buildId:data.buildId});
        }
      });
      window.__EFHC_OLD_SW_CONTROLLER_TEST__ = navigator.serviceWorker.controller;
      return navigator.serviceWorker.controller?.scriptURL || "";
    });
    assert.ok(originalController.endsWith("/sw.js"),"existing worker must control active session");
    const oldConfig=exportConfig;
    const newBuildId=oldConfig.build_id.slice(0,-1)+(oldConfig.build_id.endsWith("a")?"b":"a");
    const oldStaticCache="efhc-pwa-"+oldConfig.build_id+"-static";
    const newStaticCache="efhc-pwa-"+newBuildId+"-static";
    const pinned=/^const EFHC_PWA_BUILD_CONFIG = ([^\n]+);\n/.exec(original);
    assert.ok(pinned,"real exported worker must embed an immutable version configuration");
    const nextBuild={...JSON.parse(pinned[1]),build_id:newBuildId};
    const configFile=path.join(root,"pwa-build.json");
    const originalConfigFile=await readFile(configFile,"utf8");
    const originalHtml=new Map();
    const nextScriptName="efhc-upgrade-staged.js";
    const nextCssName="efhc-upgrade-staged.css";
    const scriptPath="_next/static/"+nextScriptName;
    const cssPath="_next/static/"+nextCssName;
    const scriptUrl="/efhc/"+scriptPath;
    const cssUrl="/efhc/"+cssPath;
    nextBuild.precache=[...nextBuild.precache,scriptUrl,cssUrl];
    const nextWorker="const EFHC_PWA_BUILD_CONFIG = "+JSON.stringify(nextBuild)+";\n"+
      original.slice(pinned[0].length)+"\n// EFHC_TEST_STAGED_VERSION_"+Date.now()+"\n"+
      'self.addEventListener("message", event => { if(event.data?.type==="SKIP_WAITING") '+
      'event.waitUntil(notifyClients({type:"TEST_SKIP_MESSAGE",buildId:EFHC_PWA_BUILD_CONFIG.build_id})); });\n';
    try {
      await writeFile(path.join(root,scriptPath),"window.__EFHC_NEW_PWA_ASSET__=true;","utf8");
      await writeFile(path.join(root,cssPath),":root { --efhc-upgrade-css-proof: updated; }","utf8");
      for (const route of nextBuild.precache.filter(url=>url.endsWith(".html"))) {
        const file=path.join(root,route.replace(/^\/efhc\//,""));
        const html=await readFile(file,"utf8");
        originalHtml.set(file,html);
        let updated=html.replace(`efhc-build-id" content="${oldConfig.build_id}"`,
          `efhc-build-id" content="${newBuildId}"`);
        assert.ok(updated.includes(`efhc-build-id" content="${newBuildId}"`),
          "A staged HTML page kept the previous release marker: "+route);
        if (route==="/efhc/index.html") {
          assert.ok(updated.includes("</head>"),"real Pages root must have a head");
          updated=updated.replace("</head>",
            `<link rel="stylesheet" href="${cssUrl}"><script defer src="${scriptUrl}"></script></head>`);
        }
        await writeFile(file,updated,"utf8");
      }
      await writeFile(configFile,JSON.stringify(nextBuild,null,2)+"\n","utf8");
      await writeFile(workerFile,nextWorker,"utf8");
      await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())?.update());
      // Wait for complete offline staging AND automatic controller takeover.
      // The running React page must remain mounted; no forced reload during
      // an in-flight USER financial interaction.
      let state = null;
      let neededDirectProbe = false;
      for (let attempt = 0; attempt < 100; attempt++) {
        // Diagnostic probe only, never count a manually forced activation as
        // automated success; this distinguishes missing client messages from
        // an SW that ignored them.
        if (attempt === 48) {
          neededDirectProbe = true;
          await page.evaluate(async () => {
            const registration = await navigator.serviceWorker.getRegistration();
            registration?.waiting?.postMessage({type:"SKIP_WAITING"});
          });
        }
        state = await page.evaluate(async names => {
          const reg = await navigator.serviceWorker.getRegistration();
          const keys = await caches.keys();
          return {
            waiting: reg?.waiting?.state || null,
            active: reg?.active?.state || null,
            installing: reg?.installing?.state || null,
            sameController: navigator.serviceWorker.controller===window.__EFHC_OLD_SW_CONTROLLER_TEST__,
            oldCache: keys.includes(names.old),
            newCache: keys.includes(names.next),
            reactRoot: Boolean(document.querySelector("#__next")),
            waitingScript: reg?.waiting?.scriptURL || null,
            cacheNames: keys.filter(key => key.startsWith("efhc-pwa-")),
            cacheEvents: window.__EFHC_PWA_EVENTS__?.slice(-8) || [],
          };
        },{old:oldStaticCache,next:newStaticCache});
        if (state.active==="activated" && state.waiting===null &&
            !state.sameController && state.newCache) break;
        await page.waitForTimeout(250);
      }
      console.log("PWA_ATOMIC_UPGRADE_STATE",JSON.stringify({...state,neededDirectProbe}));
      assert.equal(neededDirectProbe,false,
        "new Service Worker only activated after test manually triggered SKIP_WAITING");
      assert.equal(state.active,"activated","new full PWA did not automatically activate");
      assert.equal(state.waiting,null);
      assert.equal(state.sameController,false);
      assert.equal(state.reactRoot,true,"running USER app was unexpectedly reloaded");
      // The previous build stays available for old live clients, but its
      // retirement may happen sooner if their loaded assets match this build.
      assert.equal(state.newCache,true,"new offline build was not staged completely");
      // No manual reload: an already-open old React page must transition
      // automatically at an idle boundary to the new HTML, JS and CSS.
      await page.waitForFunction(()=>window.__EFHC_NEW_PWA_ASSET__===true, null, {timeout:35000});
      const pageVersion=await page.evaluate(()=>({
        marker:document.querySelector('meta[name="efhc-build-id"]')?.getAttribute("content"),
        css:getComputedStyle(document.documentElement).getPropertyValue("--efhc-upgrade-css-proof").trim(),
      }));
      assert.equal(pageVersion.marker,newBuildId,"new HTML build marker never replaced old one");
      assert.equal(pageVersion.css,"updated","new CSS not rendered after automatic upgrade");
      console.log("PWA_REAL_HTML_JS_CSS_UPGRADE",JSON.stringify(pageVersion));
      const readiness = await page.evaluate(async () => {
        const manifest = await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
        const scriptPaths = [...document.querySelectorAll("script[src]")].map(x=>new URL(x.src).pathname)
          .filter(x=>x.includes("/_next/static/"));
        return {
          manifestBuild:manifest.build_id,
          documentBuild:document.querySelector('meta[name="efhc-build-id"]')?.content,
          controller:Boolean(navigator.serviceWorker.controller),
          scripts:scriptPaths.length,
          missingAssets:scriptPaths.filter(x=>!manifest.precache.includes(x)).slice(0,5),
          events:window.__EFHC_PWA_EVENTS__?.slice(-12)||[],
        };
      });
      console.log("PWA_READY_DIAGNOSTIC",JSON.stringify(readiness));
      const after=await page.evaluate(async names=>({
        keys:await caches.keys(),
        active:(await navigator.serviceWorker.getRegistration())?.active?.state,
        controlled:Boolean(navigator.serviceWorker.controller),
        nextCache:(await (await caches.open(names.next)).keys()).length,
        root:Boolean(document.querySelector("#__next")),
      }),{next:newStaticCache});
      assert.equal(after.active,"activated");
      assert.ok(after.controlled && after.root);
      assert.ok(after.nextCache>0);
      // A verified new page must release the previous build without requiring
      // the user to clear browser data or uninstall the application.
      await page.waitForFunction(async old => !(await caches.keys()).includes(old),oldStaticCache,{timeout:15000});
      const retired = await page.evaluate(async old => ({
        keys:await caches.keys(),previousPresent:(await caches.keys()).includes(old),
      }),oldStaticCache);
      assert.equal(retired.previousPresent,false,"old build cache still persisted after a verified successor loaded");
      console.log("PWA_OLD_BUILD_RETIRED",JSON.stringify(retired));
      // B3: after retiring the last old generation, opening a completely new
      // offline tab must render ONLY the fully installed successor shell.
      const reopened = await context.newPage();
      try {
        await context.setOffline(true);
        await reopened.goto(base,{waitUntil:"domcontentloaded",timeout:25000});
        const offlineBuild = await reopened.evaluate(() => ({
          buildId:document.querySelector('meta[name="efhc-build-id"]')?.content,
          script:Boolean(window.__EFHC_NEW_PWA_ASSET__),
          css:getComputedStyle(document.documentElement)
            .getPropertyValue("--efhc-upgrade-css-proof").trim(),
          root:Boolean(document.querySelector("#__next")),
        }));
        assert.deepEqual(offlineBuild,{
          buildId:newBuildId,script:true,css:"updated",root:true,
        },"Offline reopen mixed old and new build generations");
        console.log("PWA_OFFLINE_LATEST_AFTER_RETIREMENT",JSON.stringify(offlineBuild));
      } finally {
        await context.setOffline(false);
        await reopened.close();
      }
    } finally {
      await writeFile(workerFile,original,"utf8");
      await writeFile(configFile,originalConfigFile,"utf8");
      for (const [file,html] of originalHtml) await writeFile(file,html,"utf8");
      await Promise.all([unlink(path.join(root,scriptPath)).catch(()=>undefined),
        unlink(path.join(root,cssPath)).catch(()=>undefined)]);
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
