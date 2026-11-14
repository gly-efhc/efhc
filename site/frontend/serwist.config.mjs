/** Serwist Configurator: the final EFHC GitHub Pages artifact is the source.
 * The configuration is invoked after basePath, HTML markers and CSS hashing.
 */
import {readFileSync} from "node:fs";
import path from "node:path";
import {serwist} from "@serwist/next/config";

const out=process.env.EFHC_SERWIST_EXPORT_DIR;
if(!out || !path.isAbsolute(out)) {
  throw Error("EFHC_SERWIST_EXPORT_DIR must be an absolute export path");
}
const critical=JSON.parse(readFileSync(
  path.join(out,".efhc-serwist-critical.json"),"utf8"));
if(!Array.isArray(critical) || !critical.length ||
   critical.some(entry=>!entry.url || !entry.revision)) {
  throw Error("EFHC_SERWIST_CRITICAL_MANIFEST_INVALID");
}
export default serwist({
  swSrc:path.join(out,".efhc-serwist-source.mjs"),
  swDest:path.join(out,"sw.js"),
  globDirectory:out,
  globPatterns:[],
  additionalPrecacheEntries:critical,
  precachePrerendered:false,
  maximumFileSizeToCacheInBytes:30*1024*1024,
  injectionPoint:"self.__SW_MANIFEST",
});
