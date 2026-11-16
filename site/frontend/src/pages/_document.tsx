import { Html, Head, Main, NextScript } from "next/document";

const efhcBootstrapScript = "(function(){\n  var state={ready:false},finished=false;\n  window.__EFHC_PWA_GATE__=state;\n  // The server-rendered React SplashScreen owns the visible loading surface.\n  var ready=function(){\n    if(finished)return;\n    finished=true;state.ready=true;\n    try{window.dispatchEvent(new Event(\"efhc:pwa-gate-ready\"));}catch(e){}\n  };\n  var seen=document.querySelector('meta[name=\"efhc-build-id\"]');\n  var oldBuild=seen&&seen.content;\n  var bootstrapScript=document.querySelector('script[src$=\"/public-runtime-config.js\"]');\n  var scriptPath=bootstrapScript&&bootstrapScript.getAttribute(\"src\")||\"/public-runtime-config.js\";\n  var base=scriptPath.slice(0,-\"/public-runtime-config.js\".length);\n  var now=Date.now();\n  var deadline=now+8000,hardDeadline=now+20000;\n  var sleep=function(ms){return new Promise(function(resolve){setTimeout(resolve,ms);});};\n  var buildQuery=function(url){return url+(url.indexOf(\"?\")<0?\"?\":\"&\")+\"efhc_build=\"+encodeURIComponent(oldBuild||\"unknown\");};\n  function keepReloadBounded(build){\n    try{\n      var key=\"efhc:pwa-gate-reload:\"+build;\n      var number=Number(sessionStorage.getItem(key)||0);\n      if(number>=2)return false;\n      sessionStorage.setItem(key,String(number+1));\n      return true;\n    }catch(e){return false;}\n  }\n  function getWorkerBuild(worker){\n    return new Promise(function(resolve){\n      if(!worker){resolve(null);return;}\n      var channel=new MessageChannel(),settled=false;\n      var timer=setTimeout(function(){finish(null);},700);\n      function finish(value){\n        if(settled)return;settled=true;clearTimeout(timer);\n        try{channel.port1.close();}catch(e){}\n        resolve(value);\n      }\n      channel.port1.onmessage=function(event){\n        var data=event.data||{};\n        finish(data.type===\"ACTIVE_BUILD\"?data.buildId:null);\n      };\n      try{worker.postMessage({type:\"GET_ACTIVE_BUILD\"},[channel.port2]);}\n      catch(e){finish(null);}\n    });\n  }\n  function fetchVersion(){\n    return new Promise(function(resolve){\n      var abort=new AbortController();\n      var timer=setTimeout(function(){abort.abort();resolve(null);},2500);\n      fetch(base+\"/pwa-build.json\",{cache:\"no-store\",signal:abort.signal})\n        .then(function(response){return response.ok?response.json():null;})\n        .then(function(value){clearTimeout(timer);resolve(value);},function(){clearTimeout(timer);resolve(null);});\n    });\n  }\n  async function upgrade(){\n    var target=await fetchVersion();\n    if(!target||!target.build_id||!oldBuild||target.build_id===oldBuild){ready();return;}\n    var newBuild=target.build_id;\n    if(!(\"serviceWorker\" in navigator)){\n      if(keepReloadBounded(newBuild))window.location.replace(buildQuery(location.pathname+location.search));\n      else ready();\n      return;\n    }\n    try{\n      var scope=(base||\"\")+\"/\";\n      var reg=await navigator.serviceWorker.getRegistration(scope);\n      if(!reg){\n        reg=await navigator.serviceWorker.register(base+\"/sw.js\",{scope:scope,updateViaCache:\"none\"});\n      }\n      await Promise.race([reg.update().catch(function(){}),sleep(2500)]);\n      while(Date.now()<hardDeadline){\n        var staged=reg.waiting;\n        if(staged){\n          staged.postMessage({type:\"ACTIVATE_WHEN_SAFE\",buildId:newBuild,efhcSafeToActivate:true});\n        }\n        var active=reg.active||navigator.serviceWorker.controller;\n        var runningBuild=await getWorkerBuild(active);\n        if(runningBuild===newBuild && navigator.serviceWorker.controller){\n          if(keepReloadBounded(newBuild)){window.location.reload();return;}\n          ready();return;\n        }\n        if(Date.now()>=deadline && !reg.installing && !reg.waiting)break;\n        await sleep(180);\n      }\n    }catch(e){console.warn(\"EFHC_GATE_RECOVERY\",String(e));}\n    ready();\n  }\n  // A catastrophic chunk error must be repairable before React mounts.\n  var repairStarted=false;\n  async function repairOnce(){\n    if(repairStarted)return;repairStarted=true;\n    var key=\"efhc:pwa-script-repair:\"+(oldBuild||\"unknown\");\n    try{\n      if(sessionStorage.getItem(key)===\"1\")return;\n      sessionStorage.setItem(key,\"1\");\n      var reg=await navigator.serviceWorker?.getRegistration((base||\"\")+\"/\");\n      if(reg)await Promise.race([reg.update(),sleep(2500)]);\n      location.reload();\n    }catch(e){}\n  }\n  window.addEventListener(\"error\",function(event){\n    var message=String(event.message||\"\");\n    var target=event.target;\n    if(/ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module/i.test(message)||\n       (target&&target.tagName===\"SCRIPT\"&&target.src&&target.src.includes(\"/_next/static/\"))){\n      void repairOnce();\n    }\n  },true);\n  window.addEventListener(\"unhandledrejection\",function(event){\n    if(/ChunkLoadError|Loading chunk/i.test(String(event.reason)))void repairOnce();\n  });\n  setTimeout(ready,20500);\n  void upgrade();\n})();";

export default function Document() {
  return (
    <Html lang="en" data-theme="dark">
      <Head>
        <script src="/public-runtime-config.js" />
        <meta name="theme-color" content="#0a0a0f" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover"
        />
        <meta name="color-scheme" content="dark light" />
        <meta name="format-detection" content="telephone=no" />
        <link
          rel="preload"
          as="image"
          href="/assets/efhc/responsive/efhc_coin_128.avif"
          type="image/avif"
          fetchPriority="high"
        />
        <style id="efhc-first-paint-css">
          {`
            html,body,#_next{
              min-height:100%;
              background:#0a0a0f;
              color:#fff;
            }
            body{
              margin:0;
              overflow-x:hidden;
            }
          `}
        </style>
        <script src="https://telegram.org/js/telegram-web-app.js" async />
      </Head>
      <body className="efhc-first-paint-body">
        <script dangerouslySetInnerHTML={{__html:efhcBootstrapScript}} />
        <noscript>
          <div
            style={{
              background: "#0a0a0f",
              color: "#ffffff",
              minHeight: "100vh",
              padding: "24px",
              fontFamily: "Arial, Helvetica Neue, Helvetica, sans-serif",
            }}
          >
            EFHC needs JavaScript to run the WebApp.
          </div>
        </noscript>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
