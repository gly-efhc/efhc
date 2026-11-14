/** Assemble one Serwist-only /efhc/sw.js after the real Pages export.
 * No extra SW, CDN, custom cache buckets, or bootstrap-time bulk prefetch.
 */
import {createHash} from "node:crypto";
import {readFile,writeFile,unlink} from "node:fs/promises";
import {existsSync} from "node:fs";
import {spawnSync} from "node:child_process";
import path from "node:path";

const args=process.argv.slice(2);
const arg=flag => args[args.indexOf(flag)+1];
const root=path.resolve(arg("--directory") || "");
const base=arg("--base-path") || "";
if(!/^\/[A-Za-z0-9_.-]+$/.test(base)) throw Error("Invalid scoped base path");
const localPkg=path.join(root,"..","package.json");
const sourcePkg=new URL("../../frontend/package.json",import.meta.url).pathname;
const pkgFile=path.resolve(process.env.EFHC_SERWIST_PACKAGE_JSON ||
  (existsSync(localPkg) ? localPkg : sourcePkg));
const pkgDir=path.dirname(pkgFile);
const config=JSON.parse(await readFile(path.join(root,"pwa-build.json"),"utf8"));
const critical=config.precache_critical||[];
const deferred=config.precache_deferred||[];
const all=new Set(config.precache||[]);
if(!critical.length || !deferred.length ||
   critical.length+deferred.length!==all.size ||
   critical.some(p=>!all.has(p) || !p.startsWith(base+"/")) ||
   deferred.some(p=>!all.has(p) || !p.startsWith(base+"/"))) {
  throw Error("EFHC_SERWIST_PARTITION_INVALID");
}
const entries=await Promise.all(critical.map(async url=>{
  const contents=await readFile(path.join(root,url.slice(base.length+1)));
  return {url,revision:createHash("sha256").update(contents).digest("hex")};
}));
const sourcePath=path.join(root,".efhc-serwist-source.mjs");
const manifestPath=path.join(root,".efhc-serwist-critical.json");
const template=await readFile(path.join(import.meta.dirname,"sw-serwist.js"),"utf8");
const source=template
  .replace("__EFHC_BUILD_CONFIG__",JSON.stringify(config))
  .replace("__EFHC_BASE_PATH__",JSON.stringify(base));
if(source.includes("__EFHC_BUILD_CONFIG__") ||
   source.includes("__EFHC_BASE_PATH__") ||
   !source.includes("self.__SW_MANIFEST")) {
  throw Error("EFHC_SERWIST_TEMPLATE_INVALID");
}
try {
  await writeFile(sourcePath,source);
  await writeFile(manifestPath,JSON.stringify(entries));
  const cli=path.join(pkgDir,"node_modules",".bin","serwist");
  const result=spawnSync(cli,["build",path.join(pkgDir,"serwist.config.mjs")],{
    cwd:pkgDir,
    env:{...process.env,EFHC_SERWIST_EXPORT_DIR:root},
    encoding:"utf8",
    maxBuffer:8*1024*1024,
  });
  if(result.stdout) process.stdout.write(result.stdout);
  if(result.stderr) process.stderr.write(result.stderr);
  if(result.error || result.status!==0) throw Error(
    "EFHC_SERWIST_CLI_BUILD_FAILED: "+(result.error?.message||result.status));
  const worker=await readFile(path.join(root,"sw.js"),"utf8");
  if(worker.includes("self.__SW_MANIFEST") ||
     worker.includes("__EFHC_BUILD_CONFIG__") ||
     worker.includes("importScripts(") ||
     /https:\/\/(?:storage.googleapis|cdn)/i.test(worker)) {
    throw Error("EFHC_SERWIST_OUTPUT_INVALID");
  }
  console.log("EFHC_SERWIST_CONFIGURATOR_PASS critical="+critical.length+
    " deferred="+deferred.length+" build="+config.build_id);
} finally {
  await Promise.all([unlink(sourcePath).catch(()=>{}),
    unlink(manifestPath).catch(()=>{})]);
}
