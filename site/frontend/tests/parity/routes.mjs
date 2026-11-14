import {localPagesBase} from './pages-base.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(process.env.EFHC_BROWSER_TOOLS||import.meta.url),{chromium}=require('playwright-core');
const base=localPagesBase();
const basePath=new URL(base).pathname.replace(/\/$/,'');
const entries=await fs.readdir(new URL('../../src/pages/',import.meta.url),{recursive:true});
const routes=entries.filter(p=>p.endsWith('.tsx')&&!p.startsWith('api/')&&!p.split('/').some(x=>x.startsWith('_'))).map(p=>p.replace(/\.tsx$/,'').replace(/(^|\/)index$/,'')).sort();
const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();page.setDefaultTimeout(5000);
await page.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
const results=[];let errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 for(const route of routes){
  errors=[];
  try{
   await page.goto(base+(route?route+'/':''),{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>document.getElementById('__next')?.childElementCount>0);
   await page.waitForTimeout(250);
   assert.deepEqual(errors,[],`runtime exception on ${route}`);
   const visibleText=await page.locator('body').innerText();
   assert.doesNotMatch(visibleText,/\bDEMO\b|Демо-просмотр|каноническ|каноничн|IndexedDB|Маршруты React/i,`temporary engineering copy on ${route}`);
   const links=await page.locator('a[href]').evaluateAll(nodes=>nodes.map(n=>({href:n.getAttribute('href'),disabled:n.getAttribute('aria-disabled')})));
   for(const link of links)if(link.href.startsWith('/'))assert.ok(link.href.startsWith(basePath+'/')||link.href===basePath,`unprefixed app link: ${route} ${link.href}`);
   results.push({route:'/'+route,status:'PASS',links:links.length});console.log('PASS route audit','/'+route,'links',links.length);
  }catch(e){results.push({route:'/'+route,status:'FAIL',error:e.message});console.error('FAIL route audit','/'+route,e.message)}
 }
 try{
  await page.goto(base+'web-profile/?section=providers');
  await page.locator('[data-profile-content="providers"][data-provider-route="account-providers"]').waitFor({state:'visible'});
  const providers=page.locator('.efhc-account-providers[data-provider-state-source="server-session"]');
  assert.equal(await providers.getAttribute('data-provider-auth-state'),'guest','anonymous preview must not invent a linked account');
  assert.equal(await page.locator('[data-efhc-provider-demo],[data-demo-provider-action]').count(),0,'retired provider simulation must stay removed');
  await page.locator('[data-provider-open-wallet="official-ton-connect"]').click();
  await page.locator('[data-profile-content="wallet"]').waitFor({state:'visible'});
  results.push({route:'provider-settings',status:'PASS'});console.log('PASS verified-session provider UI and official wallet link');
 }catch(e){results.push({route:'provider-settings',status:'FAIL',error:e.message});console.error('FAIL provider settings',e.message)}
 // Real same-session USER navigation and protected Admin denial; no fake login.
 try{
  await page.goto(base);await page.waitForSelector('.efhc-game-nav');await page.waitForTimeout(500);
  for(const key of ['panels','exchange','tasks','referrals','ranks','energy']){
   await page.locator(`[data-nav-key="nav.${key}"]`).click();
   const expected=key==='energy'?'/':`/${key}`;
   await page.waitForFunction(expected=>document.querySelector('.efhc-independent-shell')?.dataset.themePageRoute===expected,expected);
  }
  await page.locator('.efhc-game-header_profile-name-button').click();await page.waitForSelector('.efhc-profile-page');
  assert.equal(await page.getByRole('button',{name:/^(Admin|Админ)$/}).count(),0,'guest must not see an Admin entry');
  await page.goto(base+'admin/');
  await page.locator('[data-admin-route-guard-state="blocked"]').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-admin-primitive="page"],[data-app-navigation="exit-admin"]').count(),0,'guest reached protected Admin DOM');
  await page.goBack();await page.waitForSelector('.efhc-profile-page');
  await page.locator('[data-nav-key="nav.energy"]').click();await page.waitForSelector('.efhc-energy-stage');
  assert.equal(await page.locator('[data-admin-primitive="page"]').count(),0);
  results.push({route:'same-session-navigation',status:'PASS'});console.log('PASS same-session USER routes, denied Admin and back navigation');
 }catch(e){results.push({route:'same-session-navigation',status:'FAIL',error:e.message});console.error('FAIL same-session navigation',e.message)}
}finally{await browser.close()}
if(process.env.EFHC_PARITY_ARTIFACTS){await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});await fs.writeFile(process.env.EFHC_PARITY_ARTIFACTS+'/route-results.json',JSON.stringify({results},null,2)+'\n')}
if(results.some(x=>x.status==='FAIL'))process.exitCode=1;
