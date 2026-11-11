/** Executed against real exported React. API failure must not remove page controls. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {chromium}=createRequire(process.env.EFHC_BROWSER_TOOLS||import.meta.url)('playwright-core');
const source=fileURLToPath(new URL('../../src/pages/',import.meta.url));
const pages=(await fs.readdir(source,{recursive:true})).filter(x=>x.endsWith('.tsx')&&!x.startsWith('api/')&&!x.split('/').some(p=>p.startsWith('_')||p.startsWith('['))&&!['404.tsx','500.tsx'].includes(x));
export const staticRoutes=pages.map(x=>x.replace(/\.tsx$/,'').replace(/(^|\/)index$/,'').replace(/^\//,'')).sort();
function observe(){
 const state={seen:false,lost:false,adminSeen:false,adminReplaced:false};window.__efhcStaticObservation=state;
 const read=()=>{const main=document.querySelector('#efhc-main-content');if(main){state.seen=true;if(location.pathname.includes('/admin/')){
  const user=location.pathname.includes('/admin/users/')||location.pathname.includes('/admin/user-history/');
  const control=user?document.querySelector('[data-admin-user-profile="profile-composition"]')?.querySelector('input'):document.querySelector('[data-app-navigation="exit-admin"]');
  // Streaming HTML parsing inserts the wrapper before its children. Record a
  // removal only after the real control existed; final assertions still reject
  // routes whose controls never appeared.
  if(control)state.adminSeen=true;else if(state.adminSeen)state.adminReplaced=true;
 }}else if(state.seen&&!location.pathname.includes('/browser-shop'))state.lost=true;};
 new MutationObserver(read).observe(document,{subtree:true,childList:true});
}
async function assertSurface(page,route){
 const shop=route.startsWith('browser-shop');
 if(shop){await page.locator('[data-public-surface="browser-shop"]').waitFor({state:'visible'});assert.ok(await page.locator('button,a,input').count()>2,'Shop controls persist');return;}
 const main=page.locator('#efhc-main-content');await main.waitFor({state:'visible'});
 assert.equal(await page.locator('[data-app-render-error]').count(),0,'an error boundary is not a page');
 if(route==='hub')assert.equal(await page.locator('[data-public-surface="hub"] [data-hub-link-slot-grid]').count(),1,'empty authorized link collection keeps its fixed grid');
 else if(route==='faq')assert.ok(await page.locator('.efhc-faq-section-node').count()>0,'canonical static FAQ sections exist before network data');
 else assert.ok((await main.innerText()).trim().length>10,'actual route content remains present');
 assert.equal(await page.locator('[data-admin-client-route-guard]').count(),0,'TEST never substitutes a route with an auth screen');
 if(route==='admin'||route.startsWith('admin/')){
  // Explicit owner policy: public/anonymous Pages must never render Admin.
  // Any protected admin page is visible only with a server-attested session.
  await page.locator('[data-admin-access="denied"]').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-admin-primitive="page"]').count(),0,
    'Anonymous browser must not render protected Admin components');
  assert.equal(await page.locator('[data-app-navigation="exit-admin"]').count(),0,
    'Anonymous browser must not render Admin navigation');
  assert.equal(await page.locator('[data-admin-user-profile="profile-composition"]').count(),0,
    'Anonymous browser must not render Admin profile data');
 }else{
  assert.equal(await page.locator('.efhc-game-nav a').count(),6,'persistent six-way USER navigation');
  if(['','app'].includes(route)){assert.equal(await page.locator('[data-energy-chip]').count(),3);assert.equal(await page.locator('.efhc-energy-progress-track').count(),1);}
  if(route==='panels')assert.equal(await page.locator('[data-panel-activation-cta]').count(),1);
  if(route==='panels/portfolio')assert.equal(await page.locator('[data-panels-tab-button]').count(),2);
  if(route==='tasks')assert.equal(await page.locator('[data-public-surface="tasks"] .efhc-tasks-grid').count(),1,'actual Tasks content persists');
  if(route==='referrals'){
   assert.equal(await page.locator('[data-referrals-progress-bar]').count(),1,'progress bar must never be replaced with a loading skeleton');
   assert.equal(await page.locator('[data-referral-level-step]').count(),5,'five static level positions remain present');
  }
  if(route==='ranks')assert.equal(await page.locator('[data-ranks-my-card] [data-ranks-me="true"]').count(),1,'own rank row remains mounted');
 }
 const observation=await page.evaluate(()=>window.__efhcStaticObservation);
 assert.equal(observation?.lost,false,'page was removed after it had appeared');
 assert.equal(observation?.adminReplaced,false,'Admin content was replaced during authentication');
}
export async function verifyStaticPages({base,artifacts,widths=[390,1440],modes=['offline']}={}){
 const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
 const results=[],errors=[];
 try{
  for(const width of widths)for(const mode of modes){
   const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();page.setDefaultTimeout(4000);
   page.on('pageerror',e=>errors.push({route:page.url(),message:e.message}));await context.addInitScript(observe);
   await context.route('**/*',async r=>{
    const origin=new URL(r.request().url()).origin;
    if(origin===new URL(base).origin)return r.continue();
    if(!origin.includes('efhc-cycle0032-demo-api.onrender.com')||mode==='offline')return r.abort();
    const headers={'Access-Control-Allow-Origin':new URL(base).origin,'Access-Control-Allow-Credentials':'true','Access-Control-Allow-Methods':'GET,POST,PUT,DELETE,OPTIONS','Access-Control-Allow-Headers':r.request().headers()['access-control-request-headers']||'Authorization,Content-Type,X-EFHC-Test-CSRF'};
    if(r.request().method()==='OPTIONS')return r.fulfill({status:204,headers});
    if(mode==='slow')await page.waitForTimeout(3000).catch(()=>undefined);
    return r.fulfill({status:mode==='malformed'?200:Number(mode)||503,contentType:'application/json',headers,body:mode==='malformed'?'{}':'{"code":"TEST_API_UNAVAILABLE"}'}).catch(()=>undefined);
   });
   const routes=mode==='offline'?staticRoutes:['','panels/portfolio','referrals','admin','admin/users','admin/bank','browser-shop'];
   try{for(const route of routes){const start=Date.now();try{
    const response=await page.goto(base+(route?route+'/':''),{waitUntil:'domcontentloaded'});assert.equal(response.status(),200);
    await assertSurface(page,route);await page.waitForTimeout(200);await assertSurface(page,route);
    results.push({width,mode,route:route||'/',status:'PASS',ms:Date.now()-start});
   }catch(e){results.push({width,mode,route:route||'/',status:'FAIL',error:e.message});console.error('FAIL STATIC '+width+'/'+mode+'/'+route+': '+e.message);}}}
   finally{await context.unrouteAll({behavior:'ignoreErrors'});await context.close();}
  }
 }finally{await browser.close();if(artifacts){await fs.mkdir(artifacts,{recursive:true});await fs.writeFile(path.join(artifacts,'static-pages.json'),JSON.stringify({results,errors},null,2));}}
 assert.deepEqual(errors,[],'no uncaught page/hydration exceptions');assert.equal(results.filter(x=>x.status==='FAIL').length,0,'all routes retain their own interfaces');return results;
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 const results=await verifyStaticPages({base:process.env.EFHC_REACT_URL||'http://127.0.0.1:19247/efhc/',artifacts:process.env.EFHC_PARITY_ARTIFACTS||'/tmp/efhc-static-pages',widths:(process.env.EFHC_STATIC_WIDTHS||'390,1440').split(',').map(Number),modes:(process.env.EFHC_STATIC_MODES||'offline').split(',')});console.log('STATIC_PAGES_PASS='+results.length);
}
