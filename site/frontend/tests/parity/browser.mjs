import {localPagesBase} from './pages-base.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
// Kept outside the production dependency graph; CI installs this exact tool.
const require = createRequire(process.env.EFHC_BROWSER_TOOLS || import.meta.url);
const { chromium } = require('playwright-core');
const contract = JSON.parse(await fs.readFile(new URL('./source-interface-contract.json', import.meta.url)));
const base=localPagesBase();
const basePath=new URL(base).pathname.replace(/\/$/,'');
const browser = await chromium.launch({executablePath:process.env.CHROME_BIN || '/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
const failures=[];
const results=[];
async function check(name,fn){try{await fn();results.push({name,status:'PASS'});console.log('PASS',name);}catch(e){results.push({name,status:'FAIL'});failures.push({name,error:e.message});console.error('FAIL',name,e.message);}}
const page=await browser.newPage({viewport:{width:390,height:844}});
await page.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
let state={lang:'ru',interface_settings_version:4,color_theme_id:'CT-01',interface_variants:contract.DEFAULTS};
await page.addInitScript(()=>{if(window.name){const state=JSON.parse(window.name);state.settings_owner=JSON.parse(sessionStorage.getItem('EFHC_USER_DATA_CACHE_V1')||'null')?.owner??null;sessionStorage.setItem('EFHC_USER_SETTINGS_V1',JSON.stringify(state));localStorage.setItem('EFHC_USER_SETTINGS_V1',window.name);}});
async function load(next=state,path=''){
 state=next;
 // window.name is scoped to this local test page and contains no credentials.
 await page.evaluate(value=>{window.name=JSON.stringify(value)},state);
 await page.goto(base+path);await page.waitForSelector('.efhc-game-header[data-hs]');
 await page.waitForFunction(()=>document.querySelector('.efhc-game-header_balance')?.dataset.headerBalanceFontPx);
}
try{
 await page.goto(base);
 for(const selection of contract.REGISTRY.HS)await check(`header ${selection}`,async()=>{
  await load({...state,interface_variants:{...contract.DEFAULTS,HS:selection}});
  const expected=contract.HEADER_THEME_COMPOSITION[contract.SOURCE_STYLE.HS[selection]||selection];
  const actual=await page.evaluate(()=>({shell:document.querySelector('.efhc-game-header').dataset.hs,hb:document.querySelector('.efhc-game-header_balance').dataset.hb,sc:document.querySelector('.efhc-game-header_statuses').dataset.sc}));
  assert.deepEqual(actual,expected);
 });
 await load({...state,interface_variants:contract.DEFAULTS});
 for(const width of [320,360,390,430,768])await check(`viewport ${width}`,async()=>{
  await page.setViewportSize({width,height:844});await page.waitForTimeout(150);
  const actual=await page.evaluate(()=>{const shell=document.querySelector('.efhc-independent-shell'),nav=document.querySelector('.efhc-game-nav');return{shell:shell.getBoundingClientRect().toJSON(),nav:nav.getBoundingClientRect().toJSON(),scroll:document.documentElement.scrollWidth,viewport:innerWidth,order:[...document.styleSheets].map(s=>s.href).filter(Boolean)}});
  assert.ok(Math.abs(actual.shell.width-width)<1,JSON.stringify(actual));
  assert.ok(Math.abs(actual.nav.width-width)<3,JSON.stringify(actual));
  assert.ok(actual.scroll<=width+1,'horizontal page overflow');
  const compiledIndex=actual.order.findIndex(x=>x.includes('/_next/static/css/'));
    const frozenIndex=actual.order.findIndex(x=>/\/FRONTEND_v866(?:\.[0-9a-f]{16})?\.css(?:\?|$)/.test(x));
    assert.ok(compiledIndex>=0&&frozenIndex>compiledIndex,
      `fingerprinted frozen v866 CSS must follow compiled React CSS: ${JSON.stringify(actual.order)}`);
 });

 for(const width of [1024,1440])await check(`centered desktop ${width}`,async()=>{
  await page.setViewportSize({width,height:900});await page.waitForTimeout(100);
  const actual=await page.evaluate(()=>({shell:document.querySelector('.efhc-independent-shell').getBoundingClientRect().toJSON(),nav:document.querySelector('.efhc-game-nav').getBoundingClientRect().toJSON()}));
  assert.ok(Math.abs(actual.shell.width-390)<1,JSON.stringify(actual));
  assert.ok(Math.abs(actual.shell.x-(width-390)/2)<1,JSON.stringify(actual));
  assert.ok(Math.abs(actual.nav.width-actual.shell.width)<3,JSON.stringify(actual));
 });
 await page.setViewportSize({width:390,height:844});
 await load({...state,interface_variants:contract.DEFAULTS,color_theme_id:'CT-01'});
 await check('first-visit document and shell share the v866 theme authority',async()=>{
  const actual=await page.evaluate(()=>({theme:document.documentElement.dataset.colorThemeId,shell:document.querySelector('.efhc-independent-shell').dataset.colorThemeId,status:document.documentElement.dataset.statusColor}));
  assert.deepEqual(actual,{theme:'CT-01',shell:'CT-01',status:'SC-03'});
 });
 await page.locator('.efhc-interface-customization-button').click();
 for(const expected of contract.COLOR_THEME_CATALOG)await check(`live color ${expected.id}`,async()=>{
  await page.waitForFunction(id=>document.documentElement.dataset.colorThemeId===id,expected.id);
  const actual=await page.evaluate(()=>({accent:getComputedStyle(document.documentElement).getPropertyValue('--efhc-ct-accent').trim(),header:document.querySelector('.efhc-game-header').dataset.hs,bn:document.querySelector('.efhc-game-nav_grid').dataset.bn}));
  assert.equal(actual.accent.toUpperCase(),expected.accent.toUpperCase());
  assert.equal(actual.header,'HS-03','color changed selected header design');
  assert.equal(actual.bn,contract.SOURCE_STYLE.BN[contract.DEFAULTS.BN]);
  await page.locator('[data-color-theme-control="true"]').click();
 });
 await check('design cycle, save and reload preserve the canonical selection',async()=>{
  await page.locator('.efhc-game-header').press('ArrowRight');
  await page.waitForFunction(()=>document.querySelector('.efhc-game-header').dataset.hs==='HS-06');
  await page.locator('.efhc-interface-customization-button').click();
  await page.waitForFunction(()=>document.querySelector('.efhc-independent-shell').dataset.interfaceCustomizationMode==='idle');
  const saved=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')));
  assert.equal(saved.interface_variants.HS,'HS-02');
  await page.evaluate(()=>{window.name=''});await page.reload();
  await page.waitForFunction(()=>document.querySelector('.efhc-game-header')?.dataset.hs==='HS-06');
 });
 await load({...state,interface_variants:contract.DEFAULTS});
 for(const width of [320,360,390,430])await check(`D8 balance fits ${width}px`,async()=>{
  await page.setViewportSize({width,height:844});
  await page.waitForTimeout(100);
  const actual=await page.evaluate(()=>{const box=document.querySelector('.efhc-game-header_balance'),value=box.querySelector('.efhc-game-header_balance-value'),b=box.getBoundingClientRect(),v=value.getBoundingClientRect();return{text:value.textContent.trim(),left:v.left,right:v.right,boxLeft:b.left,boxRight:b.right}});
  assert.match(actual.text,/^\d+\.\d{8}$/);
  assert.ok(actual.left>=actual.boxLeft-1&&actual.right<=actual.boxRight+1,JSON.stringify(actual));
 });
 for(const route of ['panels','exchange','tasks','referrals','ranks','hub','faq','web-profile','browser-shop','admin'])await check(`route ${route}`,async()=>{
  await page.goto(base+route+'/');
  await page.waitForFunction(()=>!!document.querySelector('.efhc-independent-shell,.efhc-browser-shop-landing'));
  if(route==='admin'||route==='browser-shop'){
   await page.waitForTimeout(150);
   assert.equal(await page.evaluate(()=>document.documentElement.dataset.colorThemeId),undefined,'USER token owner leaked into independent renderer');
  }else{
   await page.waitForFunction(()=>document.documentElement.dataset.colorThemeId==='CT-01');
   assert.ok(await page.locator('.efhc-game-nav').isVisible());
  }
 });
 await load({...state,interface_variants:contract.DEFAULTS,color_theme_id:'CT-01'},'referrals/');
 for(const width of [320,390,1440])await check(`referral social icons load inside their buttons ${width}px`,async()=>{
  await page.setViewportSize({width,height:844});
  await page.waitForFunction(()=>[...document.querySelectorAll('[data-referral-share-kind] img')].length===5&&[...document.querySelectorAll('[data-referral-share-kind] img')].every(img=>img.complete));
  const icons=await page.locator('[data-referral-share-kind]').evaluateAll(buttons=>buttons.map(button=>{
   const img=button.querySelector('img'),box=button.getBoundingClientRect(),icon=img.getBoundingClientRect();
   return{kind:button.dataset.referralShareKind,src:img.getAttribute('src'),loaded:img.naturalWidth>0&&img.naturalHeight>0,width:icon.width,height:icon.height,inside:icon.left>=box.left&&icon.right<=box.right&&icon.top>=box.top&&icon.bottom<=box.bottom};
  }));
  assert.deepEqual(icons.map(icon=>icon.kind),['telegram','whatsapp','viber','facebook','x']);
  for(const icon of icons){
   assert.ok(icon.loaded,`broken referral icon: ${JSON.stringify(icon)}`);
   assert.equal(icon.src,new URL(`brands/${icon.kind}.svg`,base).pathname);
   assert.ok(icon.width>0&&icon.height>0&&icon.inside,`referral icon outside its button: ${JSON.stringify(icon)}`);
  }
 });
 if(process.env.EFHC_PARITY_ARTIFACTS){
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:process.env.EFHC_PARITY_ARTIFACTS+'/react-referrals-390.png',fullPage:true});
  await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});
  await load({...state,interface_variants:contract.DEFAULTS});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:process.env.EFHC_PARITY_ARTIFACTS+'/react-home-390.png'});
 }
}finally{await browser.close();}
if(failures.length){console.error(JSON.stringify(failures,null,2));process.exitCode=1;}

if(process.env.EFHC_PARITY_ARTIFACTS)await fs.writeFile(process.env.EFHC_PARITY_ARTIFACTS+'/results.json',JSON.stringify({source:contract.source,results,failures},null,2)+'\n');
