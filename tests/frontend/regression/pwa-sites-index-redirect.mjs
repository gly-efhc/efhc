import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import vm from "node:vm";
import assert from "node:assert/strict";
const server = createServer((req,res) => {
  if (req.url === "/efhc/index.html") {
    res.writeHead(308,{Location:"/efhc/"}).end();
  } else if (req.url === "/efhc/") {
    res.writeHead(200,{"Content-Type":"text/html","Content-Security-Policy":"default-src 'self'"}).end('<meta name="efhc-build-id" content="fixture"><h1>EFHC</h1>');
  } else if (req.url === "/efhc/panels/index.html") {
    res.writeHead(200,{"Content-Type":"text/html"}).end('<meta name="efhc-build-id" content="fixture"><h1>Panels</h1>');
  } else if (req.url === "/efhc/web-profile/index.html") {
    res.writeHead(307,{Location:"/other/"}).end();
  } else if (req.url === "/other/") {
    res.writeHead(200,{"Content-Type":"text/html"}).end('<meta name="efhc-build-id" content="fixture"><h1>Unexpected target</h1>');
  } else res.writeHead(404).end();
});
await new Promise(r=>server.listen(0,"127.0.0.1",r));
const origin = "http://127.0.0.1:" + server.address().port;
try {
  let routes;
  class Strategy {
    constructor(opts){this.opts=opts}
    async handle({request}) {
      const response=await fetch(request);
      const guard=this.opts?.plugins?.find(p=>p.fetchDidSucceed);
      return guard ? guard.fetchDidSucceed({response}) : response;
    }
  }
  class Serwist {
    constructor(o){routes=o.runtimeCaching}
    addEventListeners(){}
    matchPrecache(){return Promise.resolve(new Response("offline fixture"))}
  }
  let source=(await readFile(process.argv[2] ?? new URL("../../../deployment/pages-tools/sw-serwist.js", import.meta.url),"utf8")).replace(/import\s*\{[\s\S]*?\}\s*from "serwist";/,"");
  vm.runInNewContext(source,{Serwist,NetworkFirst:Strategy,NetworkOnly:Strategy,CacheFirst:Strategy,
    StaleWhileRevalidate:Strategy,ExpirationPlugin:Strategy,CacheExpiration:Strategy,
    self:{location:{origin},addEventListener(){}},URL,Response,Request,Headers,
    __EFHC_BASE_PATH__:"/efhc",__EFHC_BUILD_CONFIG__:{build_id:"fixture",precache:["/efhc/index.html","/efhc/panels/index.html","/efhc/web-profile/index.html"]}});
  const route=routes[2];
  const result=await route.handler({event:{},url:new URL(origin+"/efhc/")});
  assert.equal(result.redirected,false,"navigation must not return a followed redirect to a manual browser request");
  assert.match(await result.text(),/<h1>EFHC<\/h1>/);
  assert.equal(result.headers.get("content-security-policy"),"default-src 'self'");
  const fresh=await route.handler({event:{},url:new URL(origin+"/efhc/panels/")});
  assert.match(await fresh.text(),/<h1>Panels<\/h1>/);
  const other=await route.handler({event:{},url:new URL(origin+"/efhc/web-profile/")});
  assert.equal(await other.text(),"offline fixture");
  console.log("PASS: hosting alias returns a valid navigation response; direct page and unexpected redirect are handled separately.");
} finally { await new Promise(r=>server.close(r)); }
