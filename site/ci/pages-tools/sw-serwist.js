/* Serwist-only EFHC PWA worker. Injected after final GitHub Pages export.
 * Only the public application shell and public static assets may be cached.
 * No auth/finance APIs or advertiser media are handled by cache strategies.
 */
import {Serwist,CacheFirst,NetworkFirst,NetworkOnly,StaleWhileRevalidate,
  ExpirationPlugin} from "serwist";

const CONFIG = __EFHC_BUILD_CONFIG__;
const BASE = __EFHC_BASE_PATH__;
const expected = new Set(CONFIG.precache || []);
const deferred = new Set(CONFIG.precache_deferred || []);
const critical = new Set(CONFIG.precache_critical || []);
// A transient compatibility set, not a second cache manager or retention policy.
// Native Serwist owns every new precache/runtime entry and its expiration.
const readyClients = new Set();
const cacheNames = {
  pages:"efhc-serwist-pages",
  assets:"efhc-serwist-assets",
  media:"efhc-serwist-media",
  locale:"efhc-serwist-locale",
};
const inScope = url => url.origin === self.location.origin &&
  (url.pathname === BASE || url.pathname.startsWith(BASE + "/"));
const scoped = path => BASE + "/" + path.replace(/^\/+/, "");
const isHtml = path => path.endsWith(".html");
const isLocale = path => /\/(?:locale|faq)\/[^/]+\.json$/i.test(path);
const isMedia = path => /\.(?:png|jpe?g|svg|ico|webp|avif|mp3)$/i.test(path);
const isSensitive = path => /\/(?:api|auth|wallet|connect|tonconnect)(?:\/|$)/i.test(path);
const safePriority = value => {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value,self.location.origin);
    return inScope(url) && deferred.has(url.pathname) ? url.pathname : null;
  } catch {return null;}
};
async function notify(data) {
  for (const client of await self.clients.matchAll({type:"window",includeUncontrolled:true})) {
    try {if (inScope(new URL(client.url))) client.postMessage(data);} catch {}
  }
}
const correctHtml = async response => {
  if (!response || !response.ok) return false;
  return (await response.clone().text()).includes(
    'name="efhc-build-id" content="' + CONFIG.build_id + '"'
  );
};
const htmlGuard = {
  async fetchDidSucceed({response}) {
    if (!(await correctHtml(response))) throw Error("EFHC_HTML_GENERATION_MISMATCH");
    return response;
  },
  async cachedResponseWillBeUsed({cachedResponse}) {
    return await correctHtml(cachedResponse) ? cachedResponse : null;
  },
};
const pageStrategy = new NetworkFirst({
  cacheName:cacheNames.pages,networkTimeoutSeconds:2,plugins:[htmlGuard],
});
const assetsStrategy = new CacheFirst({cacheName:cacheNames.assets});
const mediaStrategy = new CacheFirst({
  cacheName:cacheNames.media,
  plugins:[new ExpirationPlugin({
    maxEntries:120,maxAgeSeconds:30*24*3600,purgeOnQuotaError:true,
  })],
});
const localeStrategy = new StaleWhileRevalidate({
  cacheName:cacheNames.locale,
  plugins:[new ExpirationPlugin({
    maxEntries:48,maxAgeSeconds:180*24*3600,purgeOnQuotaError:true,
  })],
});
// One-time legacy migration only. Serwist does not own caches written by
// earlier EFHC/Workbox workers. Inspect exact names AND scoped request URLs:
// never delete other applications' CacheStorage or owner-scoped data.
async function legacyPublicCaches() {
  const names = await caches.keys();
  const legacy = names.filter(name =>
    /^efhc-pwa-.+-static$/.test(name) ||
    /^efhc-public-pages-/.test(name) ||
    /^efhc-static-assets-/.test(name) ||
    name === "efhc-legacy-assets" ||
    /^workbox-precache-/.test(name));
  const safe = [];
  for (const name of legacy) {
    const entries = await (await caches.open(name)).keys();
    if ((entries.length || name.startsWith("efhc-")) &&
        entries.every(request => {
          try {return inScope(new URL(request.url));}
          catch {return false;}
        })) safe.push(name);
  }
  return safe;
}
async function retireLegacyCachesOnce() {
  const windows = (await self.clients.matchAll({
    type:"window",includeUncontrolled:true,
  })).filter(client => {
    try {return inScope(new URL(client.url));}
    catch {return false;}
  });
  if (!windows.length || windows.some(client => !readyClients.has(client.id))) {
    return;
  }
  // This runs only for legacy cache names after every scoped client has
  // attested to this generation. Native Serwist handles all later revisions.
  for (const name of await legacyPublicCaches()) await caches.delete(name);
}
async function legacyAssetFallback(request) {
  for (const name of await legacyPublicCaches()) {
    const hit = await (await caches.open(name)).match(request,{ignoreSearch:true});
    if (hit && hit.ok) return hit;
  }
  return null;
}

const networkOnly = new NetworkOnly();
const sw = new Serwist({
  precacheEntries:self.__SW_MANIFEST,
  skipWaiting:false,
  clientsClaim:true,
  navigationPreload:false,
  disableDevLogs:true,
  precacheOptions:{
    directoryIndex:"index.html",
    ignoreURLParametersMatching:[/^utm_/,/^fbclid$/],
    cleanupOutdatedCaches:true,
    concurrency:4,
  },
  runtimeCaching:[
    // Private APIs are never served from a public cache, even on failure.
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && isSensitive(url.pathname),handler:networkOnly},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && url.pathname===scoped("pwa-build.json"),handler:networkOnly},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.mode==="navigate" && inScope(url) && !isSensitive(url.pathname),
     handler:async ({event,url}) => {
       const pathname = url.pathname.endsWith(".html") ? url.pathname :
         (url.pathname.endsWith("/") ? url.pathname : url.pathname+"/") + "index.html";
       if (!expected.has(pathname)) return (await sw.matchPrecache(scoped("offline.html"))) ||
         Response.error();
       const request = new Request(new URL(pathname,url.origin),{
         credentials:"same-origin",cache:"no-store",
       });
       try {return await pageStrategy.handle({event,request});}
       catch {return (await sw.matchPrecache(scoped("offline.html"))) || Response.error();}
     }},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && deferred.has(url.pathname) && isHtml(url.pathname),
     handler:pageStrategy},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) && isLocale(url.pathname),
     handler:localeStrategy},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) && isMedia(url.pathname),
     handler:mediaStrategy},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) &&
      (/\/_next\/static\//.test(url.pathname) ||
       /\.[a-f0-9]{16}\.css$/i.test(url.pathname) ||
       (expected.has(url.pathname) && !isHtml(url.pathname))),
     handler:async ({event,request,url}) => {
       try {return await assetsStrategy.handle({event,request});}
       catch (error) {
         // A pre-Serwist open tab can still need its previous immutable JS/CSS.
         if (/\/_next\/static\//.test(url.pathname) ||
             /\.[a-f0-9]{16}\.css$/i.test(url.pathname)) {
           const prior=await legacyAssetFallback(request);
           if (prior) return prior;
         }
         throw error;
       }
     }},
  ],
});
sw.addEventListeners();

async function isCached(path) {
  if (critical.has(path)) return Boolean(await sw.matchPrecache(path));
  const name=isHtml(path)?cacheNames.pages:isLocale(path)?cacheNames.locale:
    isMedia(path)?cacheNames.media:cacheNames.assets;
  const hit=await (await caches.open(name)).match(path);
  if (!hit) return false;
  return !isHtml(path) || correctHtml(hit);
}

async function fetchDeferred(path,event) {
  if (!deferred.has(path) || await isCached(path)) return true;
  const request = new Request(new URL(path,self.location.origin),{
    credentials:"same-origin",cache:"reload",
  });
  const strategy=isHtml(path)?pageStrategy:isLocale(path)?localeStrategy:
    isMedia(path)?mediaStrategy:assetsStrategy;
  const response=await strategy.handle({event,request});
  return Boolean(response?.ok);
}
let prefetching=null;
async function prefetchDeferred(priorities=[],event) {
  if (prefetching) return prefetching;
  const preferred=priorities.map(safePriority).filter(Boolean);
  const fixed=["panels/portfolio/index.html","tasks/index.html",
    "web-profile/index.html","exchange/index.html","withdraw/index.html",
    "faq/index.html","hub/index.html","browser-shop/index.html"].map(scoped);
  const items=[...new Set([...preferred,...fixed,...CONFIG.precache_deferred])]
    .filter(path => deferred.has(path) && !/\.mp3$/i.test(path) &&
      (!isLocale(path) || /\/(?:locale|faq)\/en\.json$/i.test(path)));
  let index=0,done=0,failed=0;
  const run=async () => {
    while(index<items.length) {
      const path=items[index++];
      try {if(!(await fetchDeferred(path,event))) failed++;}
      catch {failed++;}
      done++;
      if(done%8===0||done===items.length) await notify({
        type:"CACHE_PROGRESS",reason:"deferred",completed:done,
        total:items.length,percent:Math.round(done*100/items.length),
      });
    }
  };
  prefetching=(async () => {
    await Promise.all([run(),run()]);
    await notify({type:"CACHE_COMPLETE",reason:"deferred",
      completed:done,total:items.length,failed});
  })();
  try {return await prefetching;} finally {prefetching=null;}
}

self.addEventListener("install",event => {
  event.waitUntil(notify({type:"UPDATE_AVAILABLE",buildId:CONFIG.build_id}));
});
self.addEventListener("activate",event => {
  event.waitUntil(notify({type:"UPDATE_ACTIVATED",buildId:CONFIG.build_id}));
});
self.addEventListener("message",event => {
  const data=event.data||{};
  const wait=fn => event.waitUntil(Promise.resolve().then(fn));
  if (data.type==="GET_ACTIVE_BUILD") {
    event.ports?.[0]?.postMessage({type:"ACTIVE_BUILD",buildId:CONFIG.build_id});
    return;
  }
  if(data.type==="SKIP_WAITING") {
    wait(async () => {
      if(data.buildId && data.buildId!==CONFIG.build_id) return;
      if(data.efhcSafeToActivate!==true) return;
      const windows=(await self.clients.matchAll({type:"window",includeUncontrolled:true}))
        .filter(client => {try{return inScope(new URL(client.url));}catch{return false;}});
      if(windows.length>1) return;
      await self.skipWaiting();
    });
    return;
  }
  if(data.type==="CACHE_URLS"||data.type==="PREFETCH_PRIORITY") {
    wait(() => prefetchDeferred(Array.isArray(data.urls)?data.urls:[],event));
    return;
  }
  if(data.type==="CLIENT_BUILD_READY") {
    wait(async () => {
      if (data.buildId!==CONFIG.build_id ||
          !event.source?.id || !event.source?.url ||
          !inScope(new URL(event.source.url)) ||
          !Array.isArray(data.assets) || !data.assets.length ||
          !data.assets.every(url=>typeof url==="string" && expected.has(url))) return;
      readyClients.add(event.source.id);
      await retireLegacyCachesOnce();
    });
    return;
  }
  if(data.type==="GET_CACHE_STATUS") {
    wait(async () => {
      await retireLegacyCachesOnce();
      const status=await Promise.all(CONFIG.precache.map(isCached));
      const cached=status.filter(Boolean).length;
      await notify({type:"CACHE_STATUS",buildId:CONFIG.build_id,
        precacheMissing:status.length-cached,staticEntries:cached,
        contentEntries:0,staticBytes:0,contentBytes:0});
    });
  }
});
