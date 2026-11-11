/** C0034: public Pages with original EFHC UI and real Neon TEST-backed sessions.
 * This is a smoke test: no writes, no credentials in logs or screenshots.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';

const require = createRequire(process.env.EFHC_BROWSER_TOOLS || import.meta.url);
const {chromium} = require('playwright-core');
const base = (process.env.EFHC_PAGES_URL || 'https://gly-efhc.github.io/efhc/').replace(/\/?$/, '/');
const artifacts = process.env.EFHC_PARITY_ARTIFACTS || '/tmp/efhc-c0034-pages';
await fs.mkdir(artifacts,{recursive:true});

const pagesDir=path.resolve('site/frontend/src/pages');
const entries=await fs.readdir(pagesDir,{recursive:true});
const routes=entries.filter(item=>{
  if(!item.endsWith('.tsx')||item.startsWith('api/'))return false;
  if(item.split('/').some(seg=>seg.startsWith('_')||seg.startsWith('[')))return false;
  if(['404.tsx','500.tsx'].includes(item))return false;
  return true;
}).map(item=>item.replace(/\.tsx$/,'').replace(/(^|\/)index$/,'').replace(/^\//,'')).sort();
const errors=[];
const routeChecks=[];
let browser;
let page;
try {
  for(const route of routes) {
    const url = base + (route ? route+'/' : '');
    const response = await fetch(url,{redirect:'follow',signal:AbortSignal.timeout(18000)});
    routeChecks.push({route:route||'/',status:response.status});
    assert.equal(response.status,200,'Static Pages route unavailable: '+url);
  }
  console.log('C0034_STATIC_ROUTES_PASS count='+routeChecks.length);
  browser=await chromium.launch({
    executablePath:process.env.CHROME_BIN || '/usr/bin/google-chrome',
    headless:true,
    args:['--no-sandbox','--disable-dev-shm-usage'],
  });
  const context=await browser.newContext({viewport:{width:390,height:844}});
  page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  page.setDefaultTimeout(40000);
  async function visit(route,locator){
    await page.goto(base+route,{waitUntil:'domcontentloaded',timeout:45000});
    await page.locator(locator).waitFor({state:'visible',timeout:60000});
    assert.ok(!/Application error|ZodError/.test(await page.locator('body').innerText()),'React application error on '+route);
    console.log('C0034_BROWSER_ROUTE_PASS '+route);
  }
  await visit('web-profile/','[data-profile-global-id]');
  await page.waitForFunction(() => {
    const gid=document.querySelector('[data-profile-global-id]')?.getAttribute('data-profile-global-id')||'';
    return /^\\d{10}$/.test(gid) && Number(gid)>=3001 && Number(gid)<=4000;
  },null,{timeout:60000});
  console.log('GENESIS_REAL_USER_PROFILE_ID_PASS');
  await visit('panels/','#efhc-main-content');
  const taskReads=['/api/tasks/catalog','/api/tasks/my','/api/tasks/earnings/me'].map(path=>
    page.waitForResponse(response=>new URL(response.url()).pathname===path&&response.status()===200));
  await visit('tasks/','[data-public-surface="tasks"]');
  await Promise.all(taskReads);
  await page.waitForTimeout(700);
  assert.equal(await page.locator('[data-public-surface="tasks"] .efhc-tasks-grid').count(),1,'Tasks must remain after its real data arrives');
  assert.ok(await page.locator('[data-task-card]').count()>0,'real task catalog is displayed');
  assert.equal(await page.locator('[data-app-render-error]').count(),0,'handled React failure is not a working page');
  console.log('C0036_REAL_TASKS_RENDER_AFTER_DATA_PASS');
  // Browser TEST guests must not view Admin modules.
  // Check all static routes still render their protected shell without
  // exposing privileged data or operations.
  for(const route of ['admin/','admin/users/','admin/bank/','admin/panels/','admin/reports/']) {
    const normalized='/'+route.replace(/\\/$/,'');
    await visit(route,`[data-admin-route="${normalized}"]`);
    await page.getByText('Доступ запрещён.',{exact:true}).waitFor({state:'visible',timeout:40000});
    assert.equal(await page.getByText('Административные модули',{exact:true}).count(),0,
      'Unprivileged guest can view Admin modules: '+route);
  }
  console.log('GENESIS_PROTECTED_ADMIN_ROUTES_DENIED_PASS');
  if(errors.length)throw new Error('Unhandled client exceptions: '+JSON.stringify(errors.slice(0,4)));
  console.log('GENESIS_LIVE_BROWSER_GUEST_PASS');
} catch(error) {
  console.error('GENESIS_LIVE_BROWSER_GUEST_FAILED '+String(error.message||error));
  if(page) {
    await page.screenshot({path:path.join(artifacts,'c0034-failure.png'),fullPage:true}).catch(()=>{});
  }
  process.exitCode=1;
} finally {
  await fs.writeFile(path.join(artifacts,'routes.json'),JSON.stringify({base,routeChecks,errorCount:errors.length,errors:errors.slice(0,12)},null,2));
  if(browser)await browser.close();
}
