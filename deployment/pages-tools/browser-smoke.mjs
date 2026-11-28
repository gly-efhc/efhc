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

// Pure browser-test validator. Empty/loading catalog cannot certify card geometry.
function assertTasksReadOnlySnapshot(result, requireCards) {
  if(result.runtime!=='react-server-data'||!result.hero||!result.grid||result.legacyDemo||result.overflow)
    throw Error('OWNER_TASKS_RUNTIME_OR_RESPONSIVE_FAIL '+JSON.stringify(result));
  if(!Array.isArray(result.cards)) throw Error('OWNER_TASKS_CARD_CONTRACT_INVALID');
  if(!result.cards.length) {
    if(!result.loading&&!['neutral','error'].includes(result.feedback))
      throw Error('OWNER_TASKS_EMPTY_STATE_MISSING');
    if(requireCards) throw Error('OWNER_TASKS_CATALOG_NOT_QUALIFIED: no rendered server cards');
    return;
  }
  const codes=new Set();
  for(const card of result.cards) {
    if(!card.code||!card.status||codes.has(card.code)||!['watch-ad','claim-bonus'].includes(card.action)||
      typeof card.disabled!=='boolean'||card.reward!=='bonus-efhcb'||card.asset!=='EFHCb')
      throw Error('OWNER_TASKS_CARD_CONTRACT_INVALID '+JSON.stringify(card));
    if(['unavailable','daily_limit'].includes(card.status)&&!card.disabled)
      throw Error('OWNER_TASKS_DISABLED_STATE_INVALID '+JSON.stringify(card));
    codes.add(card.code);
  }
}

// Current data contracts, independent of historical DEMO record identities.
function isD8(value) { return /^\d+\.\d{8}$/.test(value); }
function utcMillis(value) {
  const m=/^(\d{2})\.(\d{2})\.(\d{4}), (\d{2}):(\d{2}):(\d{2}) UTC$/.exec(value);
  if(!m) return NaN;
  const ms=Date.parse(`${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}:${m[6]}Z`);
  return Number.isFinite(ms)&&new Date(ms).toISOString().slice(0,19)===`${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}:${m[6]}`?ms:NaN;
}
function assertPortfolio(portfolio,tab,order) {
  if(portfolio.mode!=='portfolio-page'||portfolio.tab!==tab||portfolio.order!==order||portfolio.batch!=='20')
    throw Error('OWNER_PORTFOLIO_ROUTE_OR_BATCH_INVALID');
  if(portfolio.rows.some(r=>!/^PNL-(?!00000000$)\d{8}$/.test(r.id)||!Number.isFinite(utcMillis(r.date))||r.overflow))
    throw Error('OWNER_PORTFOLIO_CARD_DATE_GEOMETRY_REGRESSION');
  if(new Set(portfolio.ids).size!==portfolio.ids.length) throw Error('OWNER_PORTFOLIO_DUPLICATE');
  for(let i=1;i<portfolio.rows.length;i++) {
    const delta=utcMillis(portfolio.rows[i].date)-utcMillis(portfolio.rows[i-1].date);
    if(order==='oldest-first'?delta<0:delta>0) throw Error('OWNER_PORTFOLIO_SORT_INVALID');
  }
}
function assertRanksRows(rows) {
  let prev=null;
  for(const row of rows) {
    if(!Number.isSafeInteger(row.pos)||row.pos<1||!isD8(row.energy)) throw Error('OWNER_RANKS_ROW_INVALID');
    const score=BigInt(row.energy.replace('.',''));
    if(prev&&(row.pos<prev.pos||score>prev.score||(score===prev.score)!==(row.pos===prev.pos)))
      throw Error('OWNER_RANKS_SORT_OR_TIE_INVALID');
    prev={pos:row.pos,score};
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
  const expr=`JSON.stringify({href:location.href,path:location.pathname,title:document.title,text:(document.body?.innerText||'').slice(0,600),root:!!document.getElementById('__next'),html:!!document.documentElement,onboarding:!!document.querySelector('[data-onboarding-tour]'),energy:(document.querySelector('.efhc-energy-stage_value')?.textContent||'').trim(),balance:(document.querySelector('.efhc-game-header_balance-value')?.textContent||'').trim(),profileTag:(document.querySelector('.efhc-game-header_profile')?.tagName||''),profileAvatarButton:!!document.querySelector('.efhc-game-header_profile > button.efhc-game-header_profile-avatar-button'),profileNameButton:!!document.querySelector('.efhc-game-header_profile-copy > button.efhc-game-header_profile-name-button'),migration:document.querySelector('.efhc-independent-shell')?.getAttribute('data-efhc-source-styles')||'',profileDisplay:(()=>{const e=document.querySelector('.efhc-game-header_profile');return e?getComputedStyle(e).display:''})(),adminDemo:!!document.querySelector('[data-efhc-admin-readonly-demo]'),providerDemo:!!document.querySelector('[data-efhc-provider-demo=\"readonly-simulation\"]'),balanceAttr:document.querySelector('[data-header-balance-value]')?.getAttribute('data-header-balance-value'),balanceTest:document.querySelector('[data-header-balance-test]')?.getAttribute('data-header-balance-test'),adminBlocked:!!document.querySelector('[data-admin-access="denied"],[data-admin-route-guard-state="blocked"]'),adminPage:!!document.querySelector('[data-admin-primitive="page"]'),providerSource:document.querySelector('[data-provider-state-source]')?.getAttribute('data-provider-state-source'),providerAuth:document.querySelector('[data-provider-auth-state]')?.getAttribute('data-provider-auth-state'),providerStates:[...document.querySelectorAll('[data-provider-state]')].map(e=>e.getAttribute('data-provider-state'))})`;
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
    if (!isD8(data.energy)) throw Error('PAGES_ENERGY_D8_INVALID: '+data.energy);
    if (!isD8(data.balance) || data.balance!==data.balanceAttr || data.balanceTest!=='false')
      throw Error('PAGES_BALANCE_D8_OR_DISPLAY_MISMATCH: '+data.balance);
    if (data.profileTag !== 'DIV' || !data.profileAvatarButton || !data.profileNameButton) throw Error('PAGES_CANON_PROFILE_DOM_MISMATCH: '+JSON.stringify(data));
    if (data.migration !== 'true' || data.profileDisplay !== 'grid') throw Error('PAGES_CANON_PROFILE_CSS_NOT_ACTIVE: '+JSON.stringify(data));
  }
  if (path === '/admin/') {
    // A visual proof is not evidence of real role authorization.
    if(data.adminDemo) console.log('VISUAL_ONLY ADMIN: role gate not qualified by this preview');
    else if(!data.adminBlocked || data.adminPage) throw Error('PAGES_ADMIN_GUEST_GATE_INVALID');
  }
  if (path.startsWith('/web-profile/')) {
    if(data.providerDemo || data.providerSource!=='server-session' || data.providerAuth!=='guest' ||
       !data.providerStates.length || data.providerStates.some(state=>state!=='unverified'))
      throw Error('PAGES_PROVIDER_GUEST_SESSION_INVALID');
  }
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
  await inspect('/panels/portfolio/');
  const readPortfolio=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const root=document.querySelector('[data-panels-portfolio-route]');
        const list=root?.querySelector('[data-panels-scroll-mode="canonical-window"]');
        const tiles=[...(list?.querySelectorAll('[data-panel-identity]')||[])];
        const rows=tiles.map(el=>{const d=el.querySelector('[data-panel-card-field="activated-at"] .font-semibold');
          return {id:el.getAttribute('data-panel-identity'),date:d?.textContent?.trim()||'',overflow:!d||d.scrollWidth>d.clientWidth+1};});
        const top=list?.getBoundingClientRect().top;
        const visible=tiles.find(el=>el.getBoundingClientRect().bottom>top);
        return {mode:root?.getAttribute('data-panels-layout'),tab:list?.getAttribute('data-panels-list'),
          order:list?.getAttribute('data-panels-order'),batch:list?.getAttribute('data-panels-batch-size'),
          rows,ids:rows.map(r=>r.id),visibleId:visible?.getAttribute('data-panel-identity'),
          offset:visible?visible.getBoundingClientRect().top-top:null,
          nestedScroll:list?list.scrollHeight>list.clientHeight:false};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  const checkPages=async(tab,order)=>{
    let portfolio=await readPortfolio();
    assertPortfolio(portfolio,tab,order);
    if(portfolio.ids.length>20)throw Error('OWNER_PORTFOLIO_INITIAL_OVERFETCH');
    // Qualification needs confirmed data spanning successive pages, not fabricated IDs.
    if(portfolio.ids.length!==20||!portfolio.nestedScroll)
      throw Error('OWNER_PORTFOLIO_DATA_NOT_QUALIFIED: insufficient rendered first page');
    for(let page=0;page<2;page++) {
      const previous=portfolio.ids.slice(),expected=previous.length+20;
      const anchorReply=await send('Runtime.evaluate',{expression:
        `JSON.stringify((()=>{const e=document.querySelector('[data-panels-scroll-mode="canonical-window"]');
          if(!e)return null;e.scrollTop=e.scrollHeight;const top=e.getBoundingClientRect().top;
          const visible=[...e.querySelectorAll('[data-panel-identity]')].find(x=>x.getBoundingClientRect().bottom>top);
          const anchor=visible?{id:visible.getAttribute('data-panel-identity'),offset:visible.getBoundingClientRect().top-top}:null;
          e.dispatchEvent(new Event('scroll',{bubbles:true}));return anchor;})())`,returnByValue:true});
      const anchor=JSON.parse(anchorReply.result.result.value);
      for(let attempt=0;attempt<15;attempt++) {
        await sleep(200);portfolio=await readPortfolio();
        if(portfolio.ids.length>expected)throw Error('OWNER_PORTFOLIO_PAGE_OVERFETCH');
        if(portfolio.ids.length>previous.length){await sleep(450);portfolio=await readPortfolio();break;}
      }
      assertPortfolio(portfolio,tab,order);
      if(portfolio.ids.length>expected)throw Error('OWNER_PORTFOLIO_PAGE_OVERFETCH');
      if(portfolio.ids.length<=previous.length)throw Error('OWNER_PORTFOLIO_DATA_NOT_QUALIFIED: no additional page observed');
      if(previous.some((id,i)=>portfolio.ids[i]!==id)||!anchor||portfolio.visibleId!==anchor.id||Math.abs(portfolio.offset-anchor.offset)>2)
        throw Error('OWNER_PORTFOLIO_SCROLL_ANCHOR_OR_DUPLICATE');
      if(portfolio.ids.length<expected){if(page===0)throw Error('OWNER_PORTFOLIO_DATA_NOT_QUALIFIED: fewer than two additional pages');break;}
    }
  };
  await checkPages('active','oldest-first');
  await send('Runtime.evaluate',{expression:`document.querySelector('[data-panels-tab-button="archive"]')?.click()`});
  await sleep(900);
  const archive=await readPortfolio();assertPortfolio(archive,'archive','oldest-first');
  if(archive.ids.length>20)throw Error('OWNER_PORTFOLIO_INITIAL_OVERFETCH');
  await send('Runtime.evaluate',{expression:`document.querySelector('[data-panels-sort-direction="oldest"]')?.click()`});
  await sleep(900);await checkPages('archive','newest-first');
  console.log('PASS OWNER REACT PORTFOLIO PAGINATION / SORT / UTC / SCROLL');
  });
  const readRanksHero=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const root=document.querySelector('.efhc-ranks-shell[data-kg]');
        const hero=root?.querySelector('[data-ranks-hero-summary="responsive-ranks-summary"]');
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
        const myEnergy=root?.querySelector('[data-ranks-my-card] .efhc-rank-generated')?.textContent?.trim()||'';
        return {myEnergy,hero:!!hero,heroWidth:rect(hero)?.width||0,
          statCount:stats.length,fullEnergy:energy?.textContent?.trim()||'',
          energyWrapOrClip,energyFragments:energyFragments.map(r=>({width:r.width,y:r.y})),
          overflow:values.some(el=>!el||el.scrollWidth>el.clientWidth+1)||stats.some(el=>el.scrollWidth>el.clientWidth+1),
          valueClipped:values.some(el=>el&&getComputedStyle(el).overflow==='hidden'),
          statComputed:values.map(el=>el ? {overflow:getComputedStyle(el).overflow,
            textOverflow:getComputedStyle(el).textOverflow,
            whiteSpace:getComputedStyle(el).whiteSpace,
            clientWidth:el.clientWidth,scrollWidth:el.scrollWidth} : null),
          refresh:!!refresh&&!refresh.disabled,find:!!find&&!find.disabled,
          rows:scoreRows.map(e=>({pos:Number(e.querySelector('.efhc-rank-position')?.textContent?.trim()),energy:(e.querySelector('.efhc-rank-generated')?.textContent?.trim()||'').replace(/ kWh$/,'')})),hasMore:!!root?.querySelector('[data-ranks-load-more="true"]'),
          viewport:innerWidth};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  const assertRankHero=(hero,width)=>{
    if(!hero.hero||hero.statCount!==2||hero.overflow||hero.valueClipped||hero.energyWrapOrClip||
       !hero.refresh||!hero.find||hero.heroWidth>width+1||!hero.fullEnergy.endsWith(' kWh')||
       !isD8(hero.fullEnergy.slice(0,-4))||hero.fullEnergy!==hero.myEnergy)
      throw Error('OWNER_RANKS_HERO_D8_OR_GEOMETRY_INVALID');
    assertRanksRows(hero.rows);
  };
  await runIndependentCheck('ranks-responsive',async()=>{
    await inspect('/ranks/');
    for(const width of [390,360]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      await sleep(700);assertRankHero(await readRanksHero(),width);
    }
  });
  await runIndependentCheck('ranks-pagination',async()=>{
    await inspect('/ranks/');
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    let ranksHero=await readRanksHero();assertRankHero(ranksHero,390);
    if(ranksHero.rows.length>100)throw Error('OWNER_RANKS_INITIAL_OVERFETCH');
    if(!ranksHero.hasMore)throw Error('OWNER_RANKS_DATA_NOT_QUALIFIED: no next page');
    for(let page=0;page<2&&ranksHero.hasMore;page++){
      const before=ranksHero.rows.length;
      const clicked=await send('Runtime.evaluate',{expression:
        `(()=>{const b=document.querySelector('[data-ranks-load-more="true"]');if(!b||b.disabled)return false;b.click();return true;})()`,returnByValue:true});
      if(clicked.result.result.value!==true)throw Error('OWNER_RANKS_NEXT_PAGE_CLICK_FAILED');
      await sleep(1300);ranksHero=await readRanksHero();assertRankHero(ranksHero,390);
      if(ranksHero.rows.length<=before||ranksHero.rows.length>before+100)throw Error('OWNER_RANKS_PAGE_SIZE_OR_PROGRESS_INVALID');
    }
    if(!ranksHero.rows.some((row,i)=>i>0&&row.pos===ranksHero.rows[i-1].pos))
      throw Error('OWNER_RANKS_TIE_DATA_NOT_QUALIFIED');
  });
  // Current Tasks is server-driven. This probe is deliberately read-only:
  // no claims, ad playback, provider navigation or fabricated catalog entries.
  const tasksProbe=async()=>{
    const reply=await send('Runtime.evaluate',{expression:
      `JSON.stringify((()=>{const shell=document.querySelector('.efhc-independent-shell');
        const page=document.querySelector('.efhc-tasks-shell[data-tasks-page-runtime]');
        const hero=page?.querySelector('.efhc-game-hero');
        const grid=page?.querySelector('[data-tasks-list-card-layout]');
        const cards=[...(grid?.querySelectorAll('[data-task-card="earning"]')||[])];
        const buttons=cards.map(e=>e.querySelector('.efhc-task-card_bottom>button'));
        const b=cards[0]?.querySelector('.efhc-task-card_reward > span:last-child');
        const rect=e=>e?.getBoundingClientRect();
        return {runtime:page?.getAttribute('data-tasks-page-runtime'),
          hero:!!hero,grid:!!grid,legacyDemo:page?.hasAttribute('data-demo-task-mode'),
          feedback:grid?.querySelector('[data-user-feedback-kind]')?.getAttribute('data-user-feedback-kind')||null,
          loading:!!grid?.querySelector('.animate-pulse[aria-hidden="true"]'),
          cards:cards.map((e,i)=>({code:e.getAttribute('data-task-code'),status:e.getAttribute('data-task-status'),
            action:buttons[i]?.getAttribute('data-task-action'),disabled:buttons[i]?.disabled,
            reward:e.querySelector('[data-task-reward]')?.getAttribute('data-task-reward'),
            asset:e.querySelector('.efhc-task-card_reward-asset')?.textContent?.trim()})),
          heroImage:hero?getComputedStyle(hero).backgroundImage:'',
          heroRadius:hero?getComputedStyle(hero).borderRadius:'',
          themeAccent:b?getComputedStyle(b).color:'',
          overflow:cards.some((e,i)=>!buttons[i]||rect(buttons[i]).right>rect(e).right+1)||
            (page?.scrollWidth||0)>(page?.clientWidth||0)+1,
          theme:shell?.getAttribute('data-color-theme-id'),
          variant:page?.getAttribute('data-tg')};})())`,returnByValue:true});
    return JSON.parse(reply.result.result.value);
  };
  await runIndependentCheck('tasks-themes-and-variants',async()=>{
    await inspect('/tasks/');
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
          assertTasksReadOnlySnapshot(result,true);
          if(result.theme!==theme||result.variant!==tg)
            throw Error('OWNER_TASKS_THEME_VARIANT_NOT_APPLIED');
          themes.add(result.themeAccent);
          if(ti===1) variants.add(result.heroImage+'|'+result.heroRadius);
        }
      }
      if(themes.size!==10||variants.size!==4)
        throw Error('OWNER_TASKS_CT_OR_TG_NOT_DISTINCT '+width+' themes='+themes.size+' variants='+variants.size);
      console.log('PASS OWNER TASKS REACT 10 CT x 4 TG '+width);
    }
  });
  await runIndependentCheck('tasks-catalog-read-only',async()=>{
    await inspect('/tasks/');
    const result=await tasksProbe();
    assertTasksReadOnlySnapshot(result,true);
    // A rendered catalog is not proof of backend reward settlement or claims.
    console.log('PASS OWNER TASKS CARD CONTRACT (read-only, no claim qualification)');
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
