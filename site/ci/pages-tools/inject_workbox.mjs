/** Assemble one classic /sw.js from locally bundled Workbox modules.
 * Runs only after Next export, Pages basePath rewriting, CSS fingerprints and
 * efhc-build-id HTML markers are finalized. No CDN and no secondary worker.
 */
import {createHash} from "node:crypto";
import {createRequire} from "node:module";
import {readFile,writeFile,unlink} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";

const args = process.argv.slice(2);
const valueOf = key => args[args.indexOf(key)+1];
const root = path.resolve(valueOf("--directory") || "");
const base = valueOf("--base-path") || "";
if (!root || !/^\/[A-Za-z0-9_.-]+$/.test(base)) {
  throw new Error("Expected --directory and scoped --base-path");
}
const pkgPath = path.resolve(process.env.EFHC_WORKBOX_PACKAGE_JSON ||
  "site/frontend/package.json");
const pkgDir = path.dirname(pkgPath);
const require = createRequire(pkgPath);
const {rollup} = require("rollup");
const resolve = require("@rollup/plugin-node-resolve");
const replace = require("@rollup/plugin-replace");
const {injectManifest} = require("workbox-build");
const config = JSON.parse(await readFile(path.join(root,"pwa-build.json"),"utf8"));
const all = new Set(config.precache || []);
const critical = config.precache_critical || [];
const deferred = config.precache_deferred || [];
if (!critical.length || !deferred.length ||
    critical.length + deferred.length !== all.size ||
    critical.some(item=>!all.has(item)) ||
    deferred.some(item=>!all.has(item)) ||
    critical.some(item=>deferred.includes(item))) {
  throw new Error("EFHC_WORKBOX_RESOURCE_PARTITION_INVALID");
}
const entries = await Promise.all(critical.map(async url => {
  if (!url.startsWith(base + "/")) throw Error("Out-of-scope Workbox URL: " + url);
  const filepath = path.join(root,url.slice(base.length+1));
  const bytes = await readFile(filepath);
  return {url,revision:createHash("sha256").update(bytes).digest("hex")};
}));
const template = await readFile(
  path.join(path.dirname(fileURLToPath(import.meta.url)),"sw-workbox.js"),"utf8");
const source = template
  .replace("__EFHC_BUILD_CONFIG__",JSON.stringify(config))
  .replace("__EFHC_BASE_PATH__",JSON.stringify(base));
if (source.includes("__EFHC_BUILD_CONFIG__") ||
    source.includes("__EFHC_BASE_PATH__") ||
    !source.includes("self.__WB_MANIFEST")) {
  throw Error("EFHC_WORKBOX_SOURCE_INJECTION_UNSAFE");
}
const temporarySource = path.join(root,".efhc-wb-source.mjs");
const temporaryBundle = path.join(root,".efhc-wb-bundle.js");
let bundle;
try {
  await writeFile(temporarySource,source);
  bundle = await rollup({
    input:temporarySource,
    plugins:[
      resolve.nodeResolve({
        browser:true,
        modulePaths:[path.join(pkgDir,"node_modules")],
      }),
      replace.default({
        preventAssignment:true,
        values:{"process.env.NODE_ENV":JSON.stringify("production")},
      }),
    ],
    onwarn(warning, handler) {
      if (warning.code === "CIRCULAR_DEPENDENCY") return;
      handler(warning);
    },
  });
  await bundle.write({
    file:temporaryBundle,
    format:"iife",
    inlineDynamicImports:true,
  });
  await bundle.close();
  const bundled = await readFile(temporaryBundle,"utf8");
  if (!bundled.includes("self.__WB_MANIFEST") ||
      /\bimportScripts\s*\(/.test(bundled) ||
      /https:\/\/(?:storage.googleapis|cdn)/i.test(bundled)) {
    throw Error("EFHC_WORKBOX_BUNDLE_NOT_SELF_CONTAINED");
  }
  const result = await injectManifest({
    swSrc:temporaryBundle,
    swDest:path.join(root,"sw.js"),
    globDirectory:root,
    globPatterns:[],
    additionalManifestEntries:entries,
    injectionPoint:"self.__WB_MANIFEST",
    maximumFileSizeToCacheInBytes:30*1024*1024,
  });
  if (result.warnings.length || result.count !== critical.length) {
    throw Error("EFHC_WORKBOX_MANIFEST_UNEXPECTED: " +
      JSON.stringify({count:result.count,expected:critical.length,warnings:result.warnings}));
  }
  const sw = await readFile(path.join(root,"sw.js"),"utf8");
  if (sw.includes("self.__WB_MANIFEST") ||
      !sw.includes("EFHC_PWA_BUILD_CONFIG") ||
      sw.includes("__EFHC_BUILD_CONFIG__") ||
      sw.includes("__EFHC_BASE_PATH__")) {
    throw Error("EFHC_WORKBOX_DEPLOYED_SERVICE_WORKER_INCOMPLETE");
  }
  console.log("EFHC_WORKBOX_INJECT_MANIFEST_PASS critical="+critical.length+
    " deferred="+deferred.length+" bytes="+result.size);
} finally {
  if (bundle) await bundle.close().catch(()=>{});
  await Promise.all([
    unlink(temporarySource).catch(()=>{}),
    unlink(temporaryBundle).catch(()=>{}),
  ]);
}
