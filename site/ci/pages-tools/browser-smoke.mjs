// Temporary GitHub Pages React runtime smoke. No external dependencies or accounts.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

const url = process.argv[2];
if (!/^http:\/\/127\.0\.0\.1:\d+\/[A-Za-z0-9_.-]+\/$/.test(url || '')) {
  throw new Error('Smoke needs exact local project Pages URL');
}
const basePath = new URL(url).pathname.slice(0,-1);
const binary = process.env.CHROME_BIN;
if (!binary || !existsSync(binary)) throw new Error('Chrome executable missing (fail closed)');
const port = 19241;
const chrome = spawn(binary, [
  '--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
  '--no-first-run','--no-default-browser-check','--disable-background-networking',
  '--remote-allow-origins=*',`--remote-debugging-port=${port}`,
  `--user-data-dir=/tmp/efhc-pages-browser-smoke-${process.pid}`,'about:blank',
], {stdio:'ignore'});
let socket;
const pending = new Map();
let nextId = 0;
let currentRoute = '/';
let lastSnapshot = null;
let lastNavProbe = null;
const runtimeEvents = [];
const routeChecks = [];
const checkFailures = [];
const checkOutcomes = [];
async function runIndependentCheck(name, task) {
  try {
    await task();
    checkOutcomes.push({section:name,status:'PASS'});
    console.log('EFHC_BROWSER_SECTION_PASS='+name);
  } catch(error) {
    const failure={section:name, route:currentRoute,
      message:limitText(error?.message || error)};
    checkFailures.push(failure);
    checkOutcomes.push({section:name,status:'FAIL'});
    track('test-failure',name+': '+failure.message);
    console.error('::error title=EFHC '+name+'::'+failure.message);
    console.error('EFHC_BROWSER_SECTION_FAIL='+JSON.stringify(failure));
    if (/CDP timeout|CDP socket timeout|Chrome exited unexpectedly|WebSocket is not open/i.test(failure.message)) {
      throw Error('EFHC_BROWSER_INFRA_BLOCKER '+failure.message);
    }
  }
}

const diagnosticDir = process.env.EFHC_CI_DIAGNOSTIC_DIR ||
  join(process.env.RUNNER_TEMP || '/tmp', 'efhc-pages-diagnostics');
const limitText = value => String(value ?? '').slice(0, 240);
function track(kind, value) {
  if (runtimeEvents.length >= 80) return;
  runtimeEvents.push({kind, route: currentRoute, value: limitText(value)});
}
function safePath(input) {
  try {const u = new URL(input); return u.origin === 'http://127.0.0.1:19240'
    ? u.pathname : u.protocol + '//' + u.hostname + u.pathname; }
  catch {return '[invalid-url]';}
}
function diagnosticSummary(status, error) {
  return {schema: 'efhc.ci.browser-diagnostics.v1', status, stage: 'chrome-runtime',
    route: currentRoute, error: error ? limitText(error?.message || error) : null,
    checkFailures, checkOutcomes,
    lastSnapshot, lastNavProbe, routeChecks, events:runtimeEvents,
    environment:{runtime:'GitHub Pages isolated DEMO', node:process.version,
      backend:'not executed', network:'external blocked'},
    note:'No tokens, cookies, user storage, secrets, query strings or page screenshots collected.'};
}
function recordDiagnostics(status,error) {
  const summary = diagnosticSummary(status,error);
  try {mkdirSync(diagnosticDir,{recursive:true});
    writeFileSync(join(diagnosticDir,'browser-smoke.json'),JSON.stringify(summary,null,2)+'\n');}
  catch(writeError) {console.error('EFHC_CI_DIAGNOSTICS_WRITE_FAIL',limitText(writeError?.message));}
  console.log('EFHC_CI_DIAGNOSTIC_JSON='+JSON.stringify(summary));
}
function close() { try { socket?.close(); } catch {} try { chrome.kill('SIGTERM'); } catch {} }
process.on('SIGINT',()=>{close();process.exit(130)});
process.on('SIGTERM',()=>{close();process.exit(143)});
async function getJson(path, options) {
  const response=await fetch(`http://127.0.0.1:${port}${path}`, options);
  if (!response.ok) throw Error(`Chrome DevTools HTTP ${response.status}`);
  return response.json();
}
async function send(method, params={}) {
  const id=++nextId;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},12000);
    pending.set(id, {resolve:(x)=>{clearTimeout(timer);resolve(x)},reject:(e)=>{clearTimeout(timer);reject(e)}});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function inspect(path) {
  currentRoute = path;
  const address=url.replace(/\/$/,'')+path;
  await send('Page.navigate',{url:address});
  await sleep(8500);
  const expr=`JSON.stringify({href:location.href,path:location.pathname,title:document.title,text:(document.body?.innerText||'').slice(0,600),root:!!document.getElementById('__next'),html:!!document.documentElement,onboarding:!!document.querySelector('[data-onboarding-tour]'),energy:(document.querySelector('.efhc-energy-stage_value')?.textContent||'').trim(),balance:(document.querySelector('.efhc-game-header_balance-value')?.textContent||'').trim(),profileTag:(document.querySelector('.efhc-game-header_profile')?.tagName||''),profileAvatarButton:!!document.querySelector('.efhc-game-header_profile > button.efhc-game-header_profile-avatar-button'),profileNameButton:!!document.querySelector('.efhc-game-header_profile-copy > button.efhc-game-header_profile-name-button'),migration:document.querySelector('.efhc-independent-shell')?.getAttribute('data-efhc-canon-migration')||'',profileDisplay:(()=>{const e=document.querySelector('.efhc-game-header_profile');return e?getComputedStyle(e).display:''})(),adminDemo:!!document.querySelector('[data-efhc-admin-readonly-demo]'),providerDemo:!!document.querySelector('[data-efhc-provider-demo=\"readonly-simulation\"]')})`;
  const result=await send('Runtime.evaluate',{expression:expr,returnByValue:true});
  const data=JSON.parse(result.result.result.value);
  lastSnapshot = {path:data.path, title:limitText(data.title), root:data.root,
    energy:data.energy, balance:data.balance, profileTag:data.profileTag,
    profileAvatarButton:data.profileAvatarButton, profileNameButton:data.profileNameButton,
    migration:data.migration, profileDisplay:data.profileDisplay,
    adminDemo:data.adminDemo, providerDemo:data.providerDemo};
  routeChecks.push({path, actualPath:data.path, mounted:data.root,
    energy:data.energy, balance:data.balance});
  const count=data.path.split('/').filter(part=>part===basePath.slice(1)).length;
  if (count !== 1 || !data.path.startsWith(basePath+'/')) throw Error('RECURSIVE_BASEPATH_OR_REDIRECT: '+data.href);
  if (!data.root || !data.html) throw Error('REACT_MOUNT_MISSING: '+data.href);
  if (/Section not found|Internal Server Error/i.test(data.text)) throw Error('REACT_ROUTE_ERROR: '+data.text);
  if (path === '/') {
    if (data.onboarding) throw Error('PAGES_CANON_PREVIEW_OBSCURED_BY_ONBOARDING');
    if (!data.energy.startsWith('8123.')) throw Error('PAGES_FROZEN_ENERGY_FIXTURE_MISSING: '+data.energy);
    if (data.balance !== '12345678.12345678') throw Error('PAGES_FROZEN_BALANCE_FIXTURE_MISSING expected=12345678.12345678 actual='+data.balance+' route='+data.path);
    if (data.profileTag !== 'DIV' || !data.profileAvatarButton || !data.profileNameButton) throw Error('PAGES_CANON_PROFILE_DOM_MISMATCH: '+JSON.stringify(data));
    if (data.migration !== 'v872' || data.profileDisplay !== 'grid') throw Error('PAGES_CANON_PROFILE_CSS_NOT_ACTIVE: '+JSON.stringify(data));
  }
  if (path === '/admin/' && !data.adminDemo) throw Error('PAGES_ADMIN_PREVIEW_MISSING');
if (path.startsWith('/web-profile/') && !data.providerDemo) throw Error('PAGES_PROVIDER_DEMO_MISSING');
console.log('PASS HEADLESS CHROME ROUTE',data.href, 'textchars='+data.text.length);
  return data;
}
try {
  let ready=false;
  for(let attempt=0;attempt<60;attempt++) {
    if (chrome.exitCode !== null) throw Error('Chrome exited unexpectedly');
    try { await getJson('/json/version'); ready=true; break; } catch {await sleep(200)}
  }
  if(!ready)throw Error('Chrome remote debugging unavailable');
  const target=await getJson('/json/new?about:blank',{method:'PUT'});
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('CDP socket timeout')),10000);
    socket.addEventListener('open',()=>{clearTimeout(timer);resolve()},{once:true});
    socket.addEventListener('error',(e)=>{clearTimeout(timer);reject(e)},{once:true});
  });
  socket.addEventListener('message',ev=>{
    try {const m=JSON.parse(ev.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m);}}catch{}
  });
  socket.addEventListener('message',ev=>{
  try {const m=JSON.parse(ev.data);
    if(m.method==='Runtime.exceptionThrown')track('js-exception',m.params?.exceptionDetails?.text);
    if(m.method==='Runtime.consoleAPICalled' && m.params?.type==='error')
      track('console-error',m.params?.args?.map(a=>a.value||a.description||a.type).join(' '));
    if(m.method==='Network.loadingFailed' && !m.params?.canceled)
      track('request-failed',m.params?.errorText);
    if(m.method==='Network.responseReceived' && m.params?.response?.status>=400)
      track('http-error',String(m.params.response.status)+' '+safePath(m.params.response.url));
  } catch {}
});
await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await runIndependentCheck('shell-rendered-geometry',async()=>{
  await inspect('/');
  // OWNER hard gate: check RENDERED COMPUTED geometry at smartphone size.
  // Prior source-grep tests all passed while the UI regressed.
  await send('Emulation.setDeviceMetricsOverride',{
    width:390,height:844,deviceScaleFactor:1,mobile:true,
  });
  await inspect('/');
  // OWNER: geometry must be measured after genuine activity, because the
  // idle gear is intentionally hidden after three seconds.
  await send('Runtime.evaluate',{expression:"window.dispatchEvent(new Event('pointermove'))"});
  await sleep(260);
  const geometryExpr=`JSON.stringify((()=>{
    const r=(selector)=>document.querySelector(selector)?.getBoundingClientRect();
    const profile=r('.efhc-game-header_profile');
    const balance=r('.efhc-game-header_balance');
    const statuses=r('.efhc-game-header_statuses');
    const nav=r('nav[data-regression-nav-canon="v888"]');
    const item=r('.efhc-game-nav_item');
    const gearElement=document.querySelector('.efhc-interface-customization-button');
    const gear=r('.efhc-interface-customization-button');
    return {profileW:profile?.width,balanceW:balance?.width,
      navH:nav?.height,itemH:item?.height,
      navCount:document.querySelectorAll('nav[data-regression-nav-canon="v888"] .efhc-game-nav_item').length,
      gearGap:gear?window.innerWidth-gear.right:null,
      gearOpacity:gearElement?getComputedStyle(gearElement).opacity:null,
      gearState:gearElement?.getAttribute('data-visible')??null,
      statusCount:document.querySelectorAll('.efhc-game-header_statuses .efhc-game-header_status').length,
      statusWithinProfile:!!(statuses&&profile && statuses.bottom<=profile.bottom+.75 && statuses.top>=profile.top-.75),
      viewport:window.innerWidth};
  })())`;
  const geometryReply=await send('Runtime.evaluate',{expression:geometryExpr,returnByValue:true});
  const geom=JSON.parse(geometryReply.result.result.value);
  if(geom.navCount!==6 || geom.itemH < 49 || geom.itemH > 56 || geom.navH < 62)
    throw Error('OWNER_BOTTOM_NAV_RENDERED_REGRESSION '+JSON.stringify(geom));
  if(!geom.profileW || !geom.balanceW || Math.abs(geom.profileW-geom.balanceW)>1.1 || geom.statusCount!==2 || !geom.statusWithinProfile)
    throw Error('OWNER_HEADER_PROFILE_STATUS_REGRESSION '+JSON.stringify(geom));
  if(geom.gearGap===null || geom.gearGap>19 || geom.gearGap<0 || geom.gearState!=='true' || Number(geom.gearOpacity)<.95)
    throw Error('OWNER_CT_GEAR_CORNER_REGRESSION '+JSON.stringify(geom));
  // Do not skip the new idle behavior: prove that the *same* gear hides
  // after inactivity without intercepting taps.
  await sleep(3300);
  const hiddenReply=await send('Runtime.evaluate',{expression:`JSON.stringify((()=>{
    const el=document.querySelector('.efhc-interface-customization-button');
    const css=el?getComputedStyle(el):null;
    return {visible:el?.getAttribute('data-visible')??null,opacity:css?.opacity??null,
      pointerEvents:css?.pointerEvents??null};
  })())`,returnByValue:true});
  const hidden=JSON.parse(hiddenReply.result.result.value);
  if(hidden.visible!=='false' || Number(hidden.opacity)>.06 || hidden.pointerEvents!=='none')
    throw Error('OWNER_CT_GEAR_IDLE_AUTOHIDE_REGRESSION '+JSON.stringify(hidden));
  console.log('PASS OWNER RENDERED SHELL 390x844',JSON.stringify({geometry:geom,idleGear:hidden}));
  });
  await runIndependentCheck('shell-navigation-and-back',async()=>{
  await inspect('/');
  // Real React navigation and Android bridge, not a source-only check.
  // Layout.NavItem uses data-nav-key={item.key}, where the Panels item key
  // is "nav.panels" (NOT "panels"). A missing probe must fail precisely
  // rather than silently invoking optional chaining and accusing routing.
  const navProbeReply=await send('Runtime.evaluate',{expression:
    `JSON.stringify((()=>{
      const anchors=[...document.querySelectorAll('nav[data-regression-nav-canon="v888"] a[data-nav-key]')];
      const anchor=document.querySelector('nav[data-regression-nav-canon="v888"] a[data-nav-key="nav.panels"]');
      return {found:!!anchor,keys:anchors.map(a=>a.getAttribute('data-nav-key')),
        hrefPath:anchor?new URL(anchor.href,location.href).pathname:null,
        disabled:!!anchor?.hasAttribute('disabled'),
        routeBefore:location.pathname};
    })())`,returnByValue:true});
  const navProbe=JSON.parse(navProbeReply.result.result.value);
  lastNavProbe=navProbe;
  if(!navProbe.found) throw Error('OWNER_NAV_PANELS_BUTTON_MISSING '+JSON.stringify(navProbe));
  if(![basePath+'/panels',basePath+'/panels/'].includes(navProbe.hrefPath||''))
    throw Error('OWNER_NAV_PANELS_HREF_MISMATCH '+JSON.stringify(navProbe));
  const clickPanels=await send('Runtime.evaluate',{expression:
    `(()=>{const anchor=document.querySelector('nav a[data-nav-key="nav.panels"]');
      if(!anchor)return false;anchor.click();return true;})()`,returnByValue:true});
  if(clickPanels.result.result.value!==true)
    throw Error('OWNER_NAV_PANELS_CLICK_DISPATCH_FAILED '+JSON.stringify(navProbe));
  await sleep(2400);
  const pathAfterClick=await send('Runtime.evaluate',{expression:'location.pathname',returnByValue:true});
  if(pathAfterClick.result.result.value!==basePath+'/panels/')
    throw Error('OWNER_NAV_PANELS_CLICK_FAILED actual='+pathAfterClick.result.result.value+' '+JSON.stringify(navProbe));
  const bridge=await send('Runtime.evaluate',{expression:
    'typeof window.__EFHC_ANDROID_BACK__ === "function" && (window.__EFHC_ANDROID_BACK__(),true)',
    returnByValue:true});
  if(bridge.result.result.value!==true) throw Error('OWNER_ANDROID_BACK_BRIDGE_MISSING');
  await sleep(2000);
  const pathAfterBack=await send('Runtime.evaluate',{expression:'location.pathname',returnByValue:true});
  if(pathAfterBack.result.result.value!==basePath+'/')
    throw Error('OWNER_ANDROID_BACK_NAVIGATION_FAILED '+pathAfterBack.result.result.value);
  console.log('PASS OWNER NAV AND BACK end-to-end');
  });
  await runIndependentCheck('panels-activation',async()=>{
  await inspect('/panels/');
  // Recovery of cycle 0010 must be proven on the rendered React,
  // not by a JSX/CSS source-grep. v866 uses one column at <=400px
  // and two above it. Shell width must not replace viewport width.
  const panelStyleReply=await send('Runtime.evaluate',{expression:
    `JSON.stringify((()=>{const card=document.querySelector('.efhc-panels-activation-card');
      const values=card?.querySelector(':scope > .grid > .grid');
      const figures=values?[...values.querySelectorAll('.tabular-nums')]:[];
      const rect=card?.getBoundingClientRect();
      return {variant:card?.getAttribute('data-pa')||'',
        expectedColumns:matchMedia('(max-width: 400px)').matches?1:2,
        columns:values?getComputedStyle(values).gridTemplateColumns:'',
        figures:figures.map(el=>({text:el.textContent?.trim()||'',
          overflow:el.scrollWidth>el.clientWidth+1})),
        height:rect?.height||null};})())`,returnByValue:true});
  const pa=JSON.parse(panelStyleReply.result.result.value);
  if(!pa.variant)throw Error('OWNER_PANELS_ACTIVATION_VARIANT_MISSING '+JSON.stringify(pa));
  if(pa.variant==='PA-01') {
    const columns=pa.columns.trim().split(/\s+/);
    if(columns.length!==pa.expectedColumns || pa.figures.length!==2 || pa.figures.some(f=>f.overflow))
      throw Error('OWNER_PANELS_PA01_RENDERED_GEOMETRY_REGRESSION '+JSON.stringify(pa));
    console.log('PASS OWNER PANELS PA-01 RENDERED GEOMETRY',JSON.stringify(pa));
  } else {
    console.log('NOT_APPLICABLE OWNER PANELS PA-01: active independent variant',pa.variant);
  }
  });
  await runIndependentCheck('panels-portfolio',async()=>{
  // RECON_CYCLE_0011: actual React portfolio, not HTML fixture or
  // source-only tests. DEMO data must be sorted before 20-row cursor
  // pagination, preserve scroll position, expose distinct archive
  // records and keep both directions functional.
  await inspect('/panels/portfolio/');
  const readPortfolio=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const root=document.querySelector('[data-panels-portfolio-route]');
        const list=root?.querySelector('[data-panels-scroll-mode="canonical-window"]');
        const ids=[...(list?.querySelectorAll('[data-panel-identity]')||[])].map(el=>el.getAttribute('data-panel-identity'));
        const first=list?.querySelector('.efhc-panel-tile');
        const date=first?.querySelector('[data-panel-card-field="activated-at"] .font-semibold');
        const head=first?.querySelector('[data-panel-card-field="panel-id"]');
        const rect=first?.getBoundingClientRect();
        return {mode:root?.getAttribute('data-panels-layout'),tab:list?.getAttribute('data-panels-list'),
          ids,scrollTop:list?.scrollTop??null,viewport:list?.clientHeight??null,
          firstHeight:rect?.height??null,firstDate:date?.textContent?.trim()||'',
          firstText:head?.textContent?.trim()||'',
          firstDateOverflow:date?date.scrollWidth>date.clientWidth+1:null,
          nestedScroll:list?list.scrollHeight>list.clientHeight:false};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  let portfolio=await readPortfolio();
  if(portfolio.mode!=='portfolio-page'||portfolio.ids.length!==20||portfolio.ids[0]!=='PNL-000000060')
    throw Error('OWNER_PORTFOLIO_INITIAL_OLDEST_20_REGRESSION '+JSON.stringify(portfolio));
  if(!portfolio.nestedScroll||portfolio.firstDateOverflow||!/\d{2}:\d{2}:\d{2} UTC/.test(portfolio.firstDate))
    throw Error('OWNER_PORTFOLIO_CARD_DATE_GEOMETRY_REGRESSION '+JSON.stringify(portfolio));
  for(const expected of [40,60]) {
    await send('Runtime.evaluate',{expression:
      `(()=>{const e=document.querySelector('[data-panels-scroll-mode="canonical-window"]');
        if(!e)return false;e.scrollTop=e.scrollHeight;e.dispatchEvent(new Event('scroll',{bubbles:true}));return true;})()`,returnByValue:true});
    let loaded=false;
    for(let check=0;check<15;check++){
      await sleep(200);
      portfolio=await readPortfolio();
      if(portfolio.ids.length>expected)
        throw Error('OWNER_PORTFOLIO_PAGE_OVERFETCH '+JSON.stringify({expected,actual:portfolio.ids.length,tab:portfolio.tab,first:portfolio.ids[0],last:portfolio.ids.at(-1),scrollTop:portfolio.scrollTop}));
      if(portfolio.ids.length===expected){
        // 40 must remain 40 after the render/scroll events settle:
        // a single bottom gesture must not auto-fetch the third page.
        await sleep(450);
        portfolio=await readPortfolio();
        if(portfolio.ids.length>expected)
          throw Error('OWNER_PORTFOLIO_PAGE_OVERFETCH '+JSON.stringify({expected,actual:portfolio.ids.length,tab:portfolio.tab,first:portfolio.ids[0],last:portfolio.ids.at(-1),scrollTop:portfolio.scrollTop}));
        if(portfolio.ids.length===expected){loaded=true;break;}
      }
    }
    if(!loaded)throw Error('OWNER_PORTFOLIO_20_20_20_PAGE_LOAD_FAILED '+expected+' '+JSON.stringify({expected,actual:portfolio.ids.length,first:portfolio.ids[0],last:portfolio.ids.at(-1),scrollTop:portfolio.scrollTop}));
    if(portfolio.ids[0]!=='PNL-000000060'||new Set(portfolio.ids).size!==expected)
      throw Error('OWNER_PORTFOLIO_SCROLL_ANCHOR_OR_DUPLICATE '+JSON.stringify(portfolio));
  }
  await send('Runtime.evaluate',{expression:
    `(()=>{document.querySelector('[data-panels-tab-button="archive"]')?.click();return true;})()`,returnByValue:true});
  await sleep(900);
  portfolio=await readPortfolio();
  if(portfolio.tab!=='archive'||portfolio.ids.length!==20||portfolio.ids[0]!=='PNL-000000160')
    throw Error('OWNER_PORTFOLIO_ARCHIVE_OLDEST_PAGE_FAILED '+JSON.stringify(portfolio));
  await send('Runtime.evaluate',{expression:
    `(()=>{document.querySelector('[data-panels-sort-direction="oldest"]')?.click();return true;})()`,returnByValue:true});
  await sleep(900);
  portfolio=await readPortfolio();
  if(portfolio.tab!=='archive'||portfolio.ids[0]!=='PNL-000000101')
    throw Error('OWNER_PORTFOLIO_ARCHIVE_NEWEST_PAGE_FAILED '+JSON.stringify(portfolio));
  // R06-O01: a still screenshot of Archive's first 20 rows is not
  // evidence that the entire 60-row history can be reached.
  for(const expected of [40,60]){
    await send('Runtime.evaluate',{expression:
      `(()=>{const e=document.querySelector('[data-panels-scroll-mode="canonical-window"]');
        if(!e)return false;e.scrollTop=e.scrollHeight;e.dispatchEvent(new Event('scroll',{bubbles:true}));return true;})()`,returnByValue:true});
    let loaded=false;
    for(let attempt=0;attempt<15;attempt++){
      await sleep(200);portfolio=await readPortfolio();
      if(portfolio.ids.length>expected)throw Error('OWNER_PORTFOLIO_ARCHIVE_OVERFETCH '+JSON.stringify({expected,actual:portfolio.ids.length}));
      if(portfolio.ids.length===expected){await sleep(450);portfolio=await readPortfolio();
        if(portfolio.ids.length===expected){loaded=true;break;}}
    }
    if(!loaded||new Set(portfolio.ids).size!==expected||portfolio.ids[0]!=='PNL-000000101')
      throw Error('OWNER_PORTFOLIO_ARCHIVE_20_20_20_FAILED '+JSON.stringify({expected,actual:portfolio.ids.length,first:portfolio.ids[0]}));
  }
  if(portfolio.ids.at(-1)!=='PNL-000000160')
    throw Error('OWNER_PORTFOLIO_ARCHIVE_LAST_RECORD_MISSING '+JSON.stringify({last:portfolio.ids.at(-1),count:portfolio.ids.length}));
  console.log('PASS OWNER REACT PORTFOLIO DEMO 60+60 / 20+20+20 / SORT / UTC / SCROLL');
  });
  await runIndependentCheck('ranks-responsive',async()=>{
  await inspect('/ranks/');
  // RECON_CYCLE_0012: physical React Ranks hero, not synthetic CSS.
  // The existing 220-row leaderboard and its appearance are immutable
  // for this scope; check its data only, without rewriting rows.
  const readRanksHero=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const root=document.querySelector('.efhc-ranks-shell[data-kg]');
        const hero=root?.querySelector('[data-ranks-hero-summary="cycle0012-responsive"]');
        const stats=[...(hero?.querySelectorAll('.efhc-game-stat')||[])];
        const values=stats.map(el=>el.querySelector('.efhc-game-stat_value'));
        const energy=hero?.querySelector('[data-ranks-hero-energy-d8]');
        const energyRange=energy?.ownerDocument.createRange();
        if(energyRange)energyRange.selectNodeContents(energy);
        const energyFragments=energyRange?[...energyRange.getClientRects()].filter(r=>r.width>0&&r.height>0):[];
        const energyRect=energy?.getBoundingClientRect();
        const energyParentRect=energy?.parentElement?.getBoundingClientRect();
        const energyWrapOrClip=!!energy&&(
          energyFragments.length!==1||
          !!energyRect&&!!energyParentRect&&(
            energyRect.left<energyParentRect.left-1||energyRect.right>energyParentRect.right+1));
        const scoreRows=[...(root?.querySelectorAll('[data-ranks-leaderboard="paged-full"] [data-ranks-card="compact-row-32"]')||[])];
        const refresh=hero?.querySelector('[data-ranks-refresh-action]');
        const find=root?.querySelector('[data-ranks-show-me-action]');
        const rect=e=>e?.getBoundingClientRect();
        const control=JSON.parse(localStorage.getItem('efhc:react:unified-demo:v893')||'null');
        const model=control?.accounts?.[control.selected_global_id];
        const text=energy?.textContent?.trim()||'';
        const match=/^(\\d+)\\.(\\d{8}) kWh$/.exec(text);
        const d8=s=>{const m=/^(\\d+)\\.(\\d{8})$/.exec(String(s));return m?BigInt(m[1])*100000000n+BigInt(m[2]):null;};
        const shown=match?BigInt(match[1])*100000000n+BigInt(match[2]):null,max=d8(model?.total_generated_kwh);
        const energyMatchesModel=shown!==null&&max!==null&&shown>=812312345678n&&shown<=max;
        return {energyMatchesModel,modelMax:model?.total_generated_kwh,hero:!!hero,heroWidth:rect(hero)?.width||0,
          statCount:stats.length,fullEnergy:energy?.textContent?.trim()||'',
          energyWrapOrClip,energyFragments:energyFragments.map(r=>({width:r.width,y:r.y})),
          overflow:values.some(el=>!el||el.scrollWidth>el.clientWidth+1)||stats.some(el=>el.scrollWidth>el.clientWidth+1),
          valueClipped:values.some(el=>el&&getComputedStyle(el).overflow==='hidden'),
          statComputed:values.map(el=>el ? {overflow:getComputedStyle(el).overflow,
            textOverflow:getComputedStyle(el).textOverflow,
            whiteSpace:getComputedStyle(el).whiteSpace,
            clientWidth:el.clientWidth,scrollWidth:el.scrollWidth} : null),
          refresh:!!refresh&&!refresh.disabled,find:!!find&&!find.disabled,
          rows:scoreRows.length,topPositions:scoreRows.slice(0,4).map(e=>e.querySelector('.efhc-rank-position')?.textContent?.trim()),
          viewport:innerWidth};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  for(const width of [390,360]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
    await sleep(700);
    const ranksHero=await readRanksHero();
    if(!ranksHero.hero||ranksHero.statCount!==2||ranksHero.overflow||ranksHero.valueClipped||ranksHero.energyWrapOrClip||
        !ranksHero.refresh||!ranksHero.find||ranksHero.heroWidth>width+1||
        !ranksHero.energyMatchesModel||ranksHero.rows<100||
        ranksHero.topPositions[0]!=='1'||ranksHero.topPositions[1]!=='2'||ranksHero.topPositions[2]!=='2')
      throw Error('OWNER_RANKS_HERO_OR_DEMO_REGRESSION '+JSON.stringify(ranksHero));
    console.log('PASS OWNER RANKS HERO RESPONSIVE '+width,JSON.stringify(ranksHero));
  }
  });
  await runIndependentCheck('ranks-pagination',async()=>{
  await inspect('/ranks/');
  const readRanksHero=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const root=document.querySelector('.efhc-ranks-shell[data-kg]');
        const hero=root?.querySelector('[data-ranks-hero-summary="cycle0012-responsive"]');
        const stats=[...(hero?.querySelectorAll('.efhc-game-stat')||[])];
        const values=stats.map(el=>el.querySelector('.efhc-game-stat_value'));
        const energy=hero?.querySelector('[data-ranks-hero-energy-d8]');
        const energyRange=energy?.ownerDocument.createRange();
        if(energyRange)energyRange.selectNodeContents(energy);
        const energyFragments=energyRange?[...energyRange.getClientRects()].filter(r=>r.width>0&&r.height>0):[];
        const energyRect=energy?.getBoundingClientRect();
        const energyParentRect=energy?.parentElement?.getBoundingClientRect();
        const energyWrapOrClip=!!energy&&(
          energyFragments.length!==1||
          !!energyRect&&!!energyParentRect&&(
            energyRect.left<energyParentRect.left-1||energyRect.right>energyParentRect.right+1));
        const scoreRows=[...(root?.querySelectorAll('[data-ranks-leaderboard="paged-full"] [data-ranks-card="compact-row-32"]')||[])];
        const refresh=hero?.querySelector('[data-ranks-refresh-action]');
        const find=root?.querySelector('[data-ranks-show-me-action]');
        const rect=e=>e?.getBoundingClientRect();
        return {hero:!!hero,heroWidth:rect(hero)?.width||0,
          statCount:stats.length,fullEnergy:energy?.textContent?.trim()||'',
          energyWrapOrClip,energyFragments:energyFragments.map(r=>({width:r.width,y:r.y})),
          overflow:values.some(el=>!el||el.scrollWidth>el.clientWidth+1)||stats.some(el=>el.scrollWidth>el.clientWidth+1),
          valueClipped:values.some(el=>el&&getComputedStyle(el).overflow==='hidden'),
          statComputed:values.map(el=>el ? {overflow:getComputedStyle(el).overflow,
            textOverflow:getComputedStyle(el).textOverflow,
            whiteSpace:getComputedStyle(el).whiteSpace,
            clientWidth:el.clientWidth,scrollWidth:el.scrollWidth} : null),
          refresh:!!refresh&&!refresh.disabled,find:!!find&&!find.disabled,
          rows:scoreRows.length,topPositions:scoreRows.slice(0,4).map(e=>e.querySelector('.efhc-rank-position')?.textContent?.trim()),
          viewport:innerWidth};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  // Verify full 220-row DEMO pagination without touching the established row layout.
  let ranksHero=await readRanksHero();
  for(let attempt=0;attempt<4&&ranksHero.rows<220;attempt++) {
    await send('Runtime.evaluate',{expression:
      `(()=>{const b=document.querySelector('[data-ranks-load-more="true"]');
        if(!b||b.disabled)return false;b.click();return true;})()`,returnByValue:true});
    await sleep(1300);ranksHero=await readRanksHero();
  }
  if(ranksHero.rows!==220||ranksHero.energyWrapOrClip)
    throw Error('OWNER_RANKS_220_DEMO_PAGINATION_REGRESSION '+JSON.stringify(ranksHero));
  console.log('PASS OWNER RANKS 220 DEMO ITEMS');
  });
  await runIndependentCheck('tasks-themes-and-variants',async()=>{
  await inspect('/tasks/');
  // RECON_CYCLE_0013: actual compiled React task controls, not frozen HTML.
  // All modifications below are ephemeral DOM theme probes in this Chrome
  // run; source, backend, wallet, production and user settings untouched.
  const tasksProbe=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const shell=document.querySelector('.efhc-independent-shell');
        const page=document.querySelector('.efhc-tasks-shell[data-tasks-page-runtime]');
        const hero=page?.querySelector('.efhc-game-hero');
        const cards=[...(page?.querySelectorAll('[data-task-card="earning"]')||[])];
        const buttons=cards.map(e=>e.querySelector('.efhc-task-card_bottom>button'));
        const b=cards[0]?.querySelector('.efhc-task-card_reward > span:last-child');
        const rect=e=>e?.getBoundingClientRect();
        return {demo:page?.getAttribute('data-demo-task-mode'),count:cards.length,
          enabled:buttons.filter(e=>e&&!e.disabled).length,
          heroImage:hero?getComputedStyle(hero).backgroundImage:'',
          heroRadius:hero?getComputedStyle(hero).borderRadius:'',
          themeAccent:b?getComputedStyle(b).color:'',
          overflow:cards.some((e,i)=>!buttons[i]||rect(buttons[i]).right>rect(e).right+1)||
            (page?.scrollWidth||0)>(page?.clientWidth||0)+1,
          theme:shell?.getAttribute('data-color-theme-id'),
          variant:page?.getAttribute('data-tg')};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  for(const width of [360,390,430]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
    await sleep(250);
    const themes=new Set();const variants=new Set();
    for(let ti=1;ti<=10;ti++) {
      for(const tg of ['TG-01','TG-02','TG-03','TG-09']) {
        const theme='CT-'+String(ti).padStart(2,'0');
        await send('Runtime.evaluate',{expression:
          `(()=>{const r=document.querySelector('.efhc-independent-shell');
            const p=document.querySelector('.efhc-tasks-shell');
            r?.setAttribute('data-color-theme-id',${JSON.stringify(theme)});
            p?.setAttribute('data-tg',${JSON.stringify(tg)});
            return true;})()`,returnByValue:true});
        const result=await tasksProbe();
        if(result.count!==5||result.enabled!==5||result.overflow||result.demo!=='global-id-unified-preview')
          throw Error('OWNER_TASKS_RUNTIME_OR_RESPONSIVE_FAIL '+width+' '+JSON.stringify(result));
        themes.add(result.themeAccent);
        if(ti===1) variants.add(result.heroImage+'|'+result.heroRadius);
      }
    }
    if(themes.size!==10||variants.size!==4)
      throw Error('OWNER_TASKS_CT_OR_TG_NOT_DISTINCT '+width+' themes='+themes.size+' variants='+variants.size);
    console.log('PASS OWNER TASKS REACT 10 CT x 4 TG '+width);
  }
  });
  await runIndependentCheck('tasks-demo-action',async()=>{
  const tasksProbe=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const shell=document.querySelector('.efhc-independent-shell');
        const page=document.querySelector('.efhc-tasks-shell[data-tasks-page-runtime]');
        const hero=page?.querySelector('.efhc-game-hero');
        const cards=[...(page?.querySelectorAll('[data-task-card="earning"]')||[])];
        const buttons=cards.map(e=>e.querySelector('.efhc-task-card_bottom>button'));
        const b=cards[0]?.querySelector('.efhc-task-card_reward > span:last-child');
        const rect=e=>e?.getBoundingClientRect();
        return {demo:page?.getAttribute('data-demo-task-mode'),count:cards.length,
          enabled:buttons.filter(e=>e&&!e.disabled).length,
          heroImage:hero?getComputedStyle(hero).backgroundImage:'',
          heroRadius:hero?getComputedStyle(hero).borderRadius:'',
          themeAccent:b?getComputedStyle(b).color:'',
          overflow:cards.some((e,i)=>!buttons[i]||rect(buttons[i]).right>rect(e).right+1)||
            (page?.scrollWidth||0)>(page?.clientWidth||0)+1,
          theme:shell?.getAttribute('data-color-theme-id'),
          variant:page?.getAttribute('data-tg')};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  await send('Page.navigate',{url:url.replace(/\/$/,'')+'/tasks/'});
  await sleep(5000);
  const taskDemo=await tasksProbe();
  if(taskDemo.count!==5||taskDemo.enabled!==5||taskDemo.demo!=='global-id-unified-preview')
    throw Error('OWNER_TASKS_REAL_DEMO_ACTIONS_DISABLED '+JSON.stringify(taskDemo));
  // First button opens local DEMO task dialog (never real claim or Ad API).
  await send('Runtime.evaluate',{expression:
    `(()=>{document.querySelector('.efhc-tasks-shell [data-task-code="demo_join_telegram"] .efhc-task-card_bottom>button')?.click();return true})()`,returnByValue:true});
  await sleep(400);
  const taskModal=await send('Runtime.evaluate',{expression:
    `JSON.stringify({open:!!document.querySelector('[role="dialog"]'),confirm:
       [...document.querySelectorAll('[role="dialog"] button')].some(b=>b.textContent.trim()==='Подтвердить')})`,returnByValue:true});
  const taskDialog=JSON.parse(taskModal.result.result.value);
  if(!taskDialog.open||!taskDialog.confirm)
    throw Error('OWNER_TASKS_DEMO_ACTION_DIALOG_MISSING '+JSON.stringify(taskDialog));
  console.log('PASS OWNER TASKS DEMO LOCAL ACTION');
  });
  await runIndependentCheck('route-faq',async()=>{await inspect('/faq/');});
  await runIndependentCheck('route-hub',async()=>{await inspect('/hub/');});
  await runIndependentCheck('route-admin',async()=>{await inspect('/admin/');});
  await runIndependentCheck('route-provider',async()=>{await inspect('/web-profile/?section=providers');});
  console.log('EFHC_BROWSER_CHECK_SUMMARY='+JSON.stringify({
    total:checkOutcomes.length,passed:checkOutcomes.filter(x=>x.status==='PASS').length,
    failed:checkFailures.length,results:checkOutcomes}));
  if (checkFailures.length) {
    throw Error('EFHC_BROWSER_REGRESSION_AGGREGATE count='+checkFailures.length+
      ' sections='+checkFailures.map(f=>f.section).join(','));
  }
  console.log('EFHC_PAGES_CHROME_RUNTIME_SMOKE=PASS');
recordDiagnostics('PASS',null);
} catch(e) {
  console.log('EFHC_BROWSER_CHECK_SUMMARY='+JSON.stringify({
  total:checkOutcomes.length,passed:checkOutcomes.filter(x=>x.status==='PASS').length,
  failed:checkFailures.length,results:checkOutcomes,infraError:limitText(e?.message||e)}));
recordDiagnostics('FAIL',e);
console.error('::error title=EFHC browser regression::'+limitText(e?.message||e));
console.error('EFHC_PAGES_CHROME_RUNTIME_SMOKE=FAIL',e.stack||String(e));
  process.exitCode=1;
} finally {close()}
