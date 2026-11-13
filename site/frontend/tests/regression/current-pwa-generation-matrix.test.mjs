import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {createHash} from "node:crypto";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {spawnSync} from "node:child_process";
import vm from "node:vm";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const source = readFileSync(path.join(root,"public/sw.js"),"utf8");
const toolsDir = path.resolve(root, "../ci/pages-tools");
const origin = "https://efhc.example";
const scope = origin + "/efhc/";
const url = value => new URL(typeof value === "string" ? value : value.url, origin).href;

function harness() {
  const buckets=new Map();
  const clients={value:[]};
  let fetcher=async () => { throw Error("offline"); };
  const posted=[];
  const cacheStorage={
    keys:async()=>[...buckets.keys()],
    delete:async name=>buckets.delete(name),
    open:async name=>{
      if(!buckets.has(name))buckets.set(name,new Map());
      const values=buckets.get(name);
      return {
        match:async req=>values.get(url(req))?.clone(),
        put:async(req,res)=>{values.set(url(req),res.clone());},
        delete:async req=>values.delete(url(req)),
        keys:async()=>[...values.keys()].map(url=>({url})),
      };
    },
    match:async req=>{
      for(const name of buckets.keys()){
        const hit=await(await cacheStorage.open(name)).match(req);
        if(hit)return hit;
      }
      return undefined;
    },
  };
  const createClient=(id,pathname="/efhc/")=>({
    id,url:origin+pathname,postMessage:message=>posted.push({id,message}),
  });
  const seed=async (build, extras={})=>{
    const s=await cacheStorage.open("efhc-pwa-"+build+"-static");
    await s.put("/efhc/index.html",new Response("HTML "+build,{status:200}));
    for(const [key,value] of Object.entries(extras)){
      await s.put(key,new Response(value,{status:200}));
    }
    await cacheStorage.open("efhc-pwa-"+build+"-content");
    return s;
  };
  const makeWorker=(build, overrides={}, lifecycle={})=>{
    const events=new Map();
    const config={
      build_id:build,static_export:true,
      precache:["/efhc/index.html","/efhc/_next/static/"+build+".js"],
      cache_limits:{
        static:{max_entries:200,max_age_seconds:2592000,max_bytes:10485760},
        content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880},
      },
      ...overrides,
    };
    const sandbox={
      URL,Request:lifecycle.Request || Request,Response,Headers,Blob,Date,console,AbortController,setTimeout,clearTimeout,
      caches:cacheStorage,fetch:(...args)=>fetcher(...args),
      EFHC_PWA_BUILD_CONFIG:config,
      self:{
        registration:{scope,active:{}},
        location:{origin},navigator:{onLine:false},
        clients:{matchAll:async()=>clients.value,claim:async()=>undefined},
        skipWaiting:lifecycle.skipWaiting || (async()=>undefined),
        addEventListener:(name,handler)=>events.set(name,handler),
      },
    };
    vm.runInNewContext(source+"\nthis.exportsForTest={cacheFirst,navigationFallback};",sandbox,{filename:"sw.js"});
    const dispatch=async (type,extra={})=>{
      let result;
      const lifetimes=[];
      const ev={
        data:extra.data,source:extra.source,request:extra.request,
        ports:extra.ports,
        waitUntil:p=>lifetimes.push(Promise.resolve(p)),
        respondWith:p=>{result=Promise.resolve(p);},
      };
      assert.ok(events.has(type),"Missing "+type+" handler");
      events.get(type)(ev);
      await Promise.all(lifetimes);
      return result ? await result : undefined;
    };
    return {...sandbox.exportsForTest,dispatch,config};
  };
  const ready=async(worker,client,build)=>{
    await worker.dispatch("message",{source:client,data:{
      type:"CLIENT_BUILD_READY",buildId:build,
      assets:["/efhc/_next/static/"+build+".js"],
    }});
  };
  return {cacheStorage,buckets,clients,createClient,seed,makeWorker,ready,posted,
    setFetch:fn=>fetcher=fn};
}

test("T1: public CSS has release-specific immutable URLs; an old tab keeps the old style",async t=>{
  const rootDir=mkdtempSync(path.join(tmpdir(),"efhc-css-generation-"));
  t.after(()=>rmSync(rootDir,{recursive:true,force:true}));
  const put=(name,value)=>{
    const p=path.join(rootDir,name);mkdirSync(path.dirname(p),{recursive:true});
    writeFileSync(p,value,"utf8");
  };
  put("index.html",'<html><head><link rel="stylesheet" href="/efhc/visual.css"></head><body><script id="__NEXT_DATA__"></script><script src="/efhc/_next/static/main.js"></script></body></html>');
  put("_next/static/main.js",'const css="/user-shell.css";');
  put("_next/static/main.css","body{color:white}");
  put("visual.css","body{color:red}");
  put("user-shell.css","body{margin:0}");
  put("public-runtime-config.js","window.__EFHC_PUBLIC_CONFIG__={};");
  for(const name of ["sw.js","manifest.webmanifest","offline.html","offline-readonly.html"])
    copyFileSync(path.join(root,"public",name),path.join(rootDir,name));
  const run=script=>spawnSync("python3",[path.join(toolsDir,script),
    "--directory",rootDir,"--base-path","/efhc"],{encoding:"utf8"});
  const first=run("fix_pages_assets.py");
  assert.equal(first.status,0,first.stderr);
  assert.equal(run("verify_export.py").status,0,"export must verify CSS fingerprint references");
  const hashed = name=>{
    const raw=readFileSync(path.join(rootDir,name));
    return name.slice(0,-4)+"."+createHash("sha256").update(raw).digest("hex").slice(0,16)+".css";
  };
  const visual=hashed("visual.css"),shell=hashed("user-shell.css");
  const html=readFileSync(path.join(rootDir,"index.html"),"utf8");
  const js=readFileSync(path.join(rootDir,"_next/static/main.js"),"utf8");
  assert.ok(html.includes("/"+visual));
  assert.ok(js.includes("/"+shell));
  assert.ok(!html.includes('href="/efhc/visual.css"'));
  const config=JSON.parse(readFileSync(path.join(rootDir,"pwa-build.json")));
  assert.ok(config.precache.includes("/efhc/"+visual));
  assert.ok(config.precache.includes("/efhc/"+shell));
  const originalManifest=readFileSync(path.join(rootDir,"pwa-build.json"),"utf8");
  assert.equal(run("fix_pages_assets.py").status,0,"export rewrite is repeatable");
  assert.equal(readFileSync(path.join(rootDir,"pwa-build.json"),"utf8"),originalManifest);

  const h=harness(),old=h.createClient("old");
  h.clients.value=[old,h.createClient("new")];
  const aCss="/efhc/style.a1b2c3d4e5f6a7b8.css";
  const bCss="/efhc/style.fedcba9876543210.css";
  await h.seed("A",{[aCss]:"red"});
  await h.seed("B",{[bCss]:"blue"});
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  assert.equal(await(await worker.cacheFirst(new Request(origin+aCss))).text(),"red");
  assert.equal(await(await worker.cacheFirst(new Request(origin+bCss))).text(),"blue");
});

test("Removed dev/neon never falls back to legacy offline HTML",async()=>{
  const h=harness();
  const legacy=h.createClient("legacy","/efhc/panels/");
  h.clients.value=[legacy];
  await h.seed("A",{"/efhc/dev/neon/index.html":"obsolete console"});
  await h.seed("B");
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  assert.ok((await h.cacheStorage.keys()).includes("efhc-pwa-A-static"),
    "Legacy cache is retained for a still-open previous tab");
  for(const pathname of ["/efhc/dev/neon","/efhc/dev/neon/",
    "/efhc/dev/neon/index.html","/efhc/dev/neon/?utm_source=chatgpt.com"]){
    const response=await worker.dispatch("fetch",{request:{
      url:origin+pathname,method:"GET",mode:"navigate",
    }});
    assert.equal(response.status,404,pathname);
    assert.equal(await response.text(),"",pathname);
    assert.equal(response.headers.get("cache-control"),"no-store");
  }
});

test("T2: a restarted worker restores predecessor inventory before first old chunk request",async()=>{
  const h=harness(),old=h.createClient("old"),newTab=h.createClient("new");
  h.clients.value=[old,newTab];
  const chunk="/efhc/_next/static/old-only.js";
  await h.seed("A",{[chunk]:"old chunk"});
  await h.seed("B");
  await h.makeWorker("B").dispatch("activate");
  const resumed=h.makeWorker("B");
  let network=0;
  h.setFetch(async()=>{network++;throw Error("offline");});
  const r=await resumed.cacheFirst(new Request(origin+chunk));
  assert.equal(await r.text(),"old chunk");assert.equal(network,0);
});

test("T3: an unrelated origin-window cannot block scope retirement",async()=>{
  const h=harness(),current=h.createClient("current"),outsider=h.createClient("outsider","/second-app/");
  h.clients.value=[current,outsider];
  await h.seed("A");await h.seed("B");
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  await h.ready(worker,current,"B");
  assert.ok(!(await h.cacheStorage.keys()).includes("efhc-pwa-A-static"));
});

test("T4: readiness persists over worker restart without another READY message",async()=>{
  const h=harness(),current=h.createClient("current"),old=h.createClient("old","/efhc/panels/");
  h.clients.value=[current,old];
  await h.seed("A");await h.seed("B");
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  await h.ready(worker,current,"B");
  assert.ok((await h.cacheStorage.keys()).includes("efhc-pwa-A-static"));
  h.clients.value=[current];
  await h.makeWorker("B").dispatch("message",{source:current,data:{type:"GET_CACHE_STATUS"}});
  assert.ok(!(await h.cacheStorage.keys()).includes("efhc-pwa-A-static"));
});

test("T5: a closed previously-ready tab is not a permanent retirement blocker",async()=>{
  const h=harness(),first=h.createClient("first"),second=h.createClient("second");
  h.clients.value=[first,second];
  await h.seed("A");await h.seed("B");
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  await h.ready(worker,first,"B");
  h.clients.value=[first];
  await h.makeWorker("B").dispatch("message",{source:first,data:{type:"GET_CACHE_STATUS"}});
  assert.deepEqual((await h.cacheStorage.keys()).filter(k=>k==="efhc-pwa-A-static"),[]);
});

test("T6: an unready in-scope old tab retains its full old build",async()=>{
  const h=harness(),current=h.createClient("current"),legacy=h.createClient("legacy","/efhc/panels/");
  h.clients.value=[current,legacy];
  await h.seed("A");await h.seed("B");
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  await h.ready(worker,current,"B");
  assert.ok((await h.cacheStorage.keys()).includes("efhc-pwa-A-static"));
});

test("T7: A/B/C succession retains both predecessors until last legacy page closes",async()=>{
  const h=harness(),current=h.createClient("current"),legacy=h.createClient("legacy","/efhc/panels/");
  h.clients.value=[current,legacy];
  await h.seed("A");await h.seed("B");await h.seed("C");
  const worker=h.makeWorker("C");
  await worker.dispatch("activate");
  await h.ready(worker,current,"C");
  assert.ok((await h.cacheStorage.keys()).includes("efhc-pwa-A-static"));
  assert.ok((await h.cacheStorage.keys()).includes("efhc-pwa-B-static"));
  h.clients.value=[current];
  await h.makeWorker("C").dispatch("message",{source:current,data:{type:"GET_CACHE_STATUS"}});
  assert.ok(!(await h.cacheStorage.keys()).includes("efhc-pwa-A-static"));
  assert.ok(!(await h.cacheStorage.keys()).includes("efhc-pwa-B-static"));
});

test("PWA verified install retains worker lifetime until skipWaiting completes",async()=>{
  const h=harness();
  let releaseActivation=()=>undefined;
  const activation=new Promise(resolve=>{releaseActivation=resolve;});
  let requested=false;
  let finished=false;
  h.setFetch(async req=>{
    const pathname=new URL(typeof req==="string"?req:req.url,origin).pathname;
    return new Response(pathname.endsWith(".html")
      ? '<meta name="efhc-build-id" content="B">'
      : "asset",{status:200});
  });
  const worker=h.makeWorker("B",{},{
    Request: class extends Request {
      constructor(input,init){super(new URL(typeof input==="string"?input:input.url,origin),init);}
    },
    skipWaiting:()=>{requested=true;return activation;},
  });
  const installing=worker.dispatch("install").then(()=>{finished=true;});
  try{
    await new Promise(resolve=>setTimeout(resolve,40));
    assert.equal(requested,true,"full PWA precache must finish before activation");
    assert.equal(finished,false,"install event must retain activation promise");
  }finally{
    releaseActivation();
  }
  await installing;
  assert.equal(finished,true);
});

test("T8: failed install removes own incomplete generation without deleting predecessor",async()=>{
  const h=harness();await h.seed("A");
  h.setFetch(async request=>{
    if(url(request).endsWith("/index.html"))
      return new Response('<meta name="efhc-build-id" content="B">',{status:200});
    throw Error("missing chunk");
  });
  const worker=h.makeWorker("B");
  await assert.rejects(worker.dispatch("install"),/EFHC_REQUIRED_PRECACHE_FAILED/);
  const keys=await h.cacheStorage.keys();
  assert.ok(keys.includes("efhc-pwa-A-static"));
  assert.ok(!keys.includes("efhc-pwa-B-static"));
  assert.ok(!keys.includes("efhc-pwa-B-content"));
});

test("T9: online no-store build metadata is never supplied from stale content cache",async()=>{
  const h=harness();
  const old=await h.cacheStorage.open("efhc-pwa-A-content");
  await old.put("/efhc/pwa-build.json",new Response(JSON.stringify({build_id:"A"}),{status:200}));
  let calls=0;
  h.setFetch(async()=>{calls++;return new Response(JSON.stringify({build_id:"B"}),{status:200});});
  const worker=h.makeWorker("B");
  const req=new Request(origin+"/efhc/pwa-build.json",{cache:"no-store"});
  const response=await worker.dispatch("fetch",{request:req});
  assert.equal((await response.json()).build_id,"B");
  assert.equal(calls,1);
});

test("T10: emergency offline HTML is sourced from newest retained generation",async()=>{
  const h=harness(),current=h.createClient("current"),old=h.createClient("old");
  h.clients.value=[current,old];
  await h.seed("A");await h.seed("B");const c=await h.seed("C");
  const worker=h.makeWorker("C");
  await worker.dispatch("activate");
  await c.delete("/efhc/index.html");
  const response=await worker.navigationFallback(new Request(origin+"/efhc/"),{waitUntil:()=>{}});
  assert.equal(await response.text(),"HTML B");
});

test("T11: a cache owned by a second origin-sibling app is not deleted",async()=>{
  const h=harness(),current=h.createClient("current");
  h.clients.value=[current];
  await h.seed("A");await h.seed("B");
  const sibling=await h.cacheStorage.open("efhc-pwa-sibling-static");
  await sibling.put("/second-app/index.html",new Response("other app"));
  await h.cacheStorage.open("efhc-pwa-sibling-content");
  const worker=h.makeWorker("B");
  await worker.dispatch("activate");
  await h.ready(worker,current,"B");
  const keys=await h.cacheStorage.keys();
  assert.ok(keys.includes("efhc-pwa-sibling-static"));
  assert.ok(keys.includes("efhc-pwa-sibling-content"));
  assert.ok(!keys.includes("efhc-pwa-A-static"));
});

test("T12: idle reload is bounded to three attempts and reports an explicit stall",()=>{
  const runtime=readFileSync(path.join(root,"src/components/PwaRuntimeStatus.tsx"),"utf8");
  assert.match(runtime,/attempts >= 3/);
  assert.match(runtime,/lastAttemptAt/);
  assert.match(runtime,/retryDelayMs/);
  assert.match(runtime,/efhc:pwa-upgrade-stalled/);
  assert.match(runtime,/sessionStorage\.removeItem\(verifiedKey\)/);
  assert.match(runtime,/queryClient\.isMutating\(\) > 0/);
});

test("Background music stops on hide/pagehide/freeze and cannot resume while hidden",()=>{
  const audio=readFileSync(path.join(root,"src/components/BackgroundMusicController.tsx"),"utf8");
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
