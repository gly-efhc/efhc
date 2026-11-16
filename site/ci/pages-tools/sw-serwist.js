/* EFHC GitHub Pages: single Serwist Service Worker.
 * Serwist alone owns install, precache revision cleanup, runtime cache writes,
 * expiration, CACHE_URLS prefetch and waiting/activation lifecycle.
 * No EFHC CacheStorage deletion, manual GC, LRU, cache index or second engine.
 */
import {
  Serwist, CacheFirst, NetworkFirst, NetworkOnly,
  StaleWhileRevalidate, ExpirationPlugin,
} from "serwist";

const CONFIG = __EFHC_BUILD_CONFIG__;
const BASE = __EFHC_BASE_PATH__;
const expected = new Set(CONFIG.precache || []);
const inScope = url => url.origin === self.location.origin &&
  (url.pathname === BASE || url.pathname.startsWith(BASE + "/"));
const scoped = path => BASE + "/" + path.replace(/^\/+/, "");
const isHtml = path => path.endsWith(".html");
const isLocale = path => /\/(?:locale|faq)\/[^/]+\.json$/i.test(path);
const isMedia = path => /\.(?:png|jpe?g|svg|ico|webp|avif|mp3)$/i.test(path);
const isSensitive = path => /\/(?:api|auth|wallet|connect|tonconnect)(?:\/|$)/i.test(path);

// NO_SERWIST_NATIVE_EQUIVALENT: a success HTTP status alone cannot establish
// that a static Next.js document belongs to this compiled JavaScript build.
// Keep this tiny Serwist strategy plugin; it is NOT a cache manager.
const correctHtml = async response => Boolean(response?.ok) &&
  (await response.clone().text()).includes(
    'name="efhc-build-id" content="' + CONFIG.build_id + '"'
  );
const htmlGuard = {
  async fetchDidSucceed({response}) {
    if (!(await correctHtml(response))) throw Error("EFHC_HTML_GENERATION_MISMATCH");
    return response;
  },
  async cachedResponseWillBeUsed({cachedResponse}) {
    return await correctHtml(cachedResponse) ? cachedResponse : null;
  },
};

const publicPages = new NetworkFirst({
  cacheName:"efhc-serwist-pages",
  networkTimeoutSeconds:2,
  plugins:[htmlGuard],
});
const publicAssets = new CacheFirst({
  cacheName:"efhc-serwist-assets",
  plugins:[new ExpirationPlugin({maxEntries:900,purgeOnQuotaError:true})],
});
const publicLocale = new StaleWhileRevalidate({
  cacheName:"efhc-serwist-locale",
  plugins:[new ExpirationPlugin({maxEntries:48,maxAgeSeconds:180*24*3600,purgeOnQuotaError:true})],
});
const publicMedia = new CacheFirst({
  cacheName:"efhc-serwist-media",
  plugins:[new ExpirationPlugin({maxEntries:120,maxAgeSeconds:30*24*3600,purgeOnQuotaError:true})],
});
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
    // Private authentication and financial requests are always network-only.
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && isSensitive(url.pathname),handler:networkOnly},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && url.pathname===scoped("pwa-build.json"),handler:networkOnly},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.mode==="navigate" && inScope(url) && !isSensitive(url.pathname),
      handler:async ({event,url}) => {
        // Pages Router exports /route/index.html; Serwist still owns caching.
        const pathname=url.pathname.endsWith(".html") ? url.pathname :
          (url.pathname.endsWith("/")?url.pathname:url.pathname+"/")+"index.html";
        if (!expected.has(pathname))
          return (await sw.matchPrecache(scoped("offline.html"))) || Response.error();
        const request = new Request(new URL(pathname,url.origin), {
          credentials:"same-origin",cache:"no-store",
        });
        try {return await publicPages.handle({event,request});}
        catch {return (await sw.matchPrecache(scoped("offline.html"))) || Response.error();}
      }},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) && expected.has(url.pathname) &&
      isHtml(url.pathname),handler:publicPages},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) && isLocale(url.pathname),
      handler:publicLocale},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) && isMedia(url.pathname),
      handler:publicMedia},
    {matcher:({request,url,sameOrigin}) => sameOrigin &&
      request.method==="GET" && inScope(url) &&
      (/\/_next\/static\//.test(url.pathname) ||
       /\.[a-f0-9]{16}\.css$/i.test(url.pathname) ||
       (expected.has(url.pathname) && !isHtml(url.pathname))),
      handler:publicAssets},
  ],
});

// Native Serwist handles SKIP_WAITING, CACHE_URLS, precache revisions, and
// activation; all old EFHC-specific message handlers/legacy GC are retired.
sw.addEventListeners();
