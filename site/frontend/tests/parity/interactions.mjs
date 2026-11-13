import {localPagesBase} from './pages-base.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {readProgressMaterial,readProgressAccent,readProgressAppearance,readProgressGeometry} from './progress-material.mjs';
import {verifyIndicators} from './indicators.mjs';
import {verifyPanelsActivationReference} from './panels-activation.mjs';
import {verifyPanelsHeroTemplates,verifyPortfolioColors} from './panels-templates.mjs';
import {verifyUserHeight} from './user-height.mjs';
import {verifyUiFollowup} from './ui-followup.mjs';
import {verifyProgress20Grid} from './progress-grid.mjs';
import {expectedSelectionOrder} from './progress-order.mjs';
const require=createRequire(process.env.EFHC_BROWSER_TOOLS||import.meta.url);
const {chromium}=require('playwright-core');
const canon=JSON.parse(await fs.readFile(new URL('./source-interface-contract.json',import.meta.url)));
const base=localPagesBase();
const basePath=new URL(base).pathname.replace(/\/$/,'');
if(process.env.EFHC_PARITY_ARTIFACTS)await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
const results=[];
async function check(name,run,{width=390,height=844,telegram=false,settings={}}={}){
 const context=await browser.newContext({viewport:{width,height}});
 const page=await context.newPage();page.setDefaultTimeout(5000);
 await page.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
 await page.addInitScript(({defaults,settings,telegram})=>{
  if(!localStorage.getItem('EFHC_USER_SETTINGS_V1')) localStorage.setItem('EFHC_USER_SETTINGS_V1',JSON.stringify({lang:'ru',interface_settings_version:4,color_theme_id:'CT-01',interface_variants:defaults,music_enabled:false,...settings}));
  if(telegram){
   const listeners=new Set();window.__efhcHostTest={closed:0,back:()=>[...listeners].forEach(fn=>fn())};
   window.Telegram={WebApp:{platform:'android',initData:'',initDataUnsafe:{},themeParams:{},ready(){},expand(){},onEvent(){},offEvent(){},close(){window.__efhcHostTest.closed++},BackButton:{show(){},hide(){},onClick(fn){listeners.add(fn)},offClick(fn){listeners.delete(fn)}}}};
  }
 },{defaults:canon.DEFAULTS,settings,telegram});
 try{await run(page);results.push({name,status:'PASS'});console.log('PASS',name)}catch(e){results.push({name,status:'FAIL',error:e.message});console.error('FAIL',name,e.message);
  if(process.env.EFHC_PARITY_ARTIFACTS){
   const dir=process.env.EFHC_PARITY_ARTIFACTS;await fs.mkdir(dir,{recursive:true});
   const label=`interaction-fail-${results.length}`;
   await fs.writeFile(`${dir}/${label}.json`,JSON.stringify({name,error:e.message,url:page.url()},null,2));
   await fs.writeFile(`${dir}/${label}.html`,await page.content()).catch(()=>{});
   await page.screenshot({path:`${dir}/${label}.png`,fullPage:true}).catch(()=>{});
  }
 }finally{await context.close()}
}
async function open(page,route=''){
 await page.goto(base+route,{waitUntil:'domcontentloaded'});
 await page.waitForSelector('.efhc-game-header');
 await page.waitForFunction(()=>typeof window.__EFHC_ANDROID_BACK__==='function');
 await page.waitForFunction(()=>!document.querySelector('.efhc-entry-splash:not([aria-hidden="true"]),.efhc-splash-breathe')||document.documentElement.dataset.efhcShell==='ready');
 await page.waitForTimeout(450);
}
const routePath=page=>page.evaluate(prefix=>location.pathname.slice(prefix.length).replace(/\/$/,'')||'/',basePath);
try{
 await check('USER adaptive height, fixed navigation and unchanged panel tiles',async page=>{
  await verifyUserHeight(page,{open,artifacts:process.env.EFHC_PARITY_ARTIFACTS});
 });
 for(const width of [320,390,1440])await check(`24 shared models: identical appearance, symmetric fills and protected starters at ${width}px`,async page=>{
  const donors=new Map();
  const reference=await page.context().newPage();
  try{
   await open(reference,'referrals/');await reference.mouse.move(12,12);
   await reference.locator('.efhc-interface-customization-button').click();
   const rp=reference.locator('[data-interface-variant-group="RP"]');
   const referenceOrder=expectedSelectionOrder('RP',canon);
   // CT-07 disables backdrop blur globally. Compare donor and candidate under
   // the same active CT instead of treating the CT-01 material as universal.
   for(let theme=0;theme<10;theme++){
    for(let offset=0;offset<referenceOrder.length;offset++){
     const id=referenceOrder[(theme+offset)%referenceOrder.length];
     const physical=canon.SOURCE_STYLE.RP[id]||id;
     assert.equal(await rp.getAttribute('data-pb'),physical);
     const refTrack=rp.locator('.efhc-energy-progress-track');
     const geometry=await refTrack.evaluate(readProgressGeometry);
     assert.ok(geometry.bounds.every(b=>b.inside),`${physical} Referrals clipping`);
     assert.ok(geometry.bounds[0].rendered<=.1,`${physical} Referrals zero width`);
     if([13,19,23,24].includes((theme+offset)%referenceOrder.length+1)){
      const full=geometry.bounds[2];
      for(const edge of ['left','right','top','bottom'])assert.ok(Math.abs(full[edge]-2)<=.1,`${physical} Referrals ${edge} inset: ${full[edge]}`);
     }
     donors.set(`${theme}/${physical}`,{material:await refTrack.evaluate(readProgressMaterial),appearance:await refTrack.evaluate(readProgressAppearance)});
     await rp.press('ArrowRight');
    }
    if(theme<9)await reference.locator('[data-color-theme-control="true"]').click();
   }
  }finally{await reference.close()}
  assert.equal(donors.size,240);
  await open(page);await page.mouse.move(12,12);
  await page.locator('.efhc-interface-customization-button').click();
  const surface=page.locator('[data-interface-variant-group="PB"]'),track=surface.locator('.efhc-energy-progress-track');
  const order=expectedSelectionOrder('PB',canon),measurements=[];
  for(let theme=0;theme<10;theme++){
   await page.waitForFunction(theme=>document.documentElement.dataset.colorThemeId==='CT-'+String(theme+1).padStart(2,'0'),theme);
   assert.equal(await track.getAttribute('data-pb'),canon.SOURCE_STYLE.PB[order[theme]]||order[theme]);
   const starter=await track.evaluate(el=>{
    const read=()=>{const t=getComputedStyle(el),f=getComputedStyle(el.firstElementChild);return {height:el.getBoundingClientRect().height,fillHeight:el.firstElementChild.getBoundingClientRect().height,background:t.backgroundImage,color:t.backgroundColor,border:t.borderColor,radius:t.borderRadius,shadow:t.boxShadow,fill:f.backgroundImage,fillColor:f.backgroundColor,fillShadow:f.boxShadow}};
    const sheet=[...document.styleSheets].find(s=>
      s.ownerNode?.getAttribute?.('data-efhc-visual-adapter')==='progress-models'
    );
    assert(sheet,'progress stylesheet missing from compiled export');
    const actual=read();const disabled=sheet.disabled;
    try{sheet.disabled=true;return {actual,withoutNonStarterSheet:read()}}finally{sheet.disabled=disabled}
   });
   assert.deepEqual(starter.actual,starter.withoutNonStarterSheet,'protected CT starter changed');
   // Start from position one in every CT; verify all 24 against the other route.
   for(let i=0;i<theme;i++)await surface.press('ArrowLeft');
   for(let i=0;i<order.length;i++){
    const physical=canon.SOURCE_STYLE.PB[order[i]]||order[i];
    assert.equal(await track.getAttribute('data-pb'),physical);
    assert.match(await surface.getAttribute('aria-label'),new RegExp(`: ${i+1} из ${order.length}\\.`));
    const reference=donors.get(`${theme}/${physical}`);
    assert.deepEqual(await track.evaluate(readProgressMaterial),reference.material,`${physical} route material differs`);
    assert.deepEqual(await track.evaluate(readProgressAppearance),reference.appearance,`${physical} route appearance differs`);
    if(i>=10){
    const accent=await track.evaluate(readProgressAccent);
    assert.ok(accent.differences.length>0,`${physical} has no CT foreground`);
    assert.ok(accent.differences.every(d=>d<5),`${physical} foreground differs from active CT: ${JSON.stringify(accent)}`);
    }
    const actual=await track.evaluate(readProgressGeometry);
    if([13,19,23,24].includes(i+1)){
     const full=actual.bounds[2];
     for(const edge of ['left','right','top','bottom'])assert.ok(Math.abs(full[edge]-2)<=.1,`${physical} Energy ${edge} inset: ${full[edge]}`);
    }
    assert.ok(actual.height>=starter.actual.height*.85&&actual.height<=starter.actual.height*1.15,`${physical} rail ${actual.height} / ${starter.actual.height}`);
    assert.ok(actual.fillHeight>=starter.actual.fillHeight*.85&&actual.fillHeight<=starter.actual.fillHeight*1.15,`${physical} fill ${actual.fillHeight} / ${starter.actual.fillHeight}`);
    assert.ok(actual.bounds.every(x=>x.inside),`${physical} escapes at 0/100%: ${JSON.stringify(actual.bounds)}`);
    assert.ok(actual.bounds[0].rendered<=.1,'zero progress has a visible width');
    measurements.push({theme:theme+1,position:i+1,physical,...actual});
    if(process.env.EFHC_PARITY_ARTIFACTS&&width===390&&theme===0&&i>=10){
     await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});
     await track.evaluate(el=>el.firstElementChild.style.width='55%');
     await track.screenshot({path:`${process.env.EFHC_PARITY_ARTIFACTS}/energy-new-${i+1}-390.png`});
    }
    if(i<order.length-1)await surface.press('ArrowRight');
   }
   if(theme<9)await page.locator('[data-color-theme-control="true"]').click();
  }
  if(process.env.EFHC_PARITY_ARTIFACTS){await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});await fs.writeFile(`${process.env.EFHC_PARITY_ARTIFACTS}/energy-cleanup-${width}.json`,JSON.stringify(measurements,null,2));}
 },{width});
 for(const width of [320,390,1440])await check(`model20 painted segment pitch survives low progress and resize at ${width}px`,async page=>{
  for(const [route,group]of [['','PB'],['referrals/','RP']]){
   await open(page,route);await page.mouse.move(12,12);
   await page.locator('.efhc-interface-customization-button').click();
   const surface=page.locator(`[data-interface-variant-group="${group}"]`);
   for(let i=0;i<19;i++)await surface.press('ArrowRight');
   await verifyProgress20Grid(page,surface.locator('.efhc-energy-progress-track'),{group,width,artifacts:process.env.EFHC_PARITY_ARTIFACTS});
  }
 },{width});
 for(const ct of ['CT-03','CT-10'])await check(`removed saved Energy model falls back to ${ct} canon and preserves Referrals`,async page=>{
  await open(page);
  const index=Number(ct.slice(-2))-1,selected=expectedSelectionOrder('PB',canon)[index];
  await page.waitForFunction(physical=>document.querySelector('[data-interface-variant-group="PB"]')?.dataset.pb===physical,canon.SOURCE_STYLE.PB[selected]||selected);
  await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();await page.locator('.efhc-interface-customization-button').click();
  const saved=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')));
  assert.equal(saved.color_theme_id,ct);assert.equal(saved.interface_variants.PB,selected);assert.equal(saved.interface_variants.RP,'RP-04');assert.equal(saved.interface_variants.HS,'HS-02');
  await page.reload();await page.waitForFunction(physical=>document.querySelector('[data-interface-variant-group="PB"]')?.dataset.pb===physical,canon.SOURCE_STYLE.PB[selected]||selected);
 },{settings:{color_theme_id:ct,interface_variants:{...canon.DEFAULTS,PB:'PB-03',RP:'RP-04',HS:'HS-02'}}});
 for(const ct of ['CT-03','CT-10'])await check(`removed Referrals model falls back to ${ct} canon without changing Energy`,async page=>{
  await open(page,'referrals/');
  const index=Number(ct.slice(-2))-1,selected=expectedSelectionOrder('RP',canon)[index];
  const physical=canon.SOURCE_STYLE.RP[selected];
  await page.waitForFunction(physical=>document.querySelector('[data-interface-variant-group="RP"]')?.dataset.pb===physical,physical);
  await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();await page.locator('.efhc-interface-customization-button').click();
  const saved=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')));
  assert.equal(saved.color_theme_id,ct);assert.equal(saved.interface_variants.RP,selected);assert.equal(saved.interface_variants.PB,'PB-04');assert.equal(saved.interface_variants.HS,'HS-02');
  await page.reload();await page.waitForFunction(physical=>document.querySelector('[data-interface-variant-group="RP"]')?.dataset.pb===physical,physical);
 },{settings:{color_theme_id:ct,interface_variants:{...canon.DEFAULTS,PB:'PB-04',RP:'RP-03',HS:'HS-02'}}});
 await check('shared library saves two independent choices across routes and reload',async page=>{
  const choose=async(group,position)=>{await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();const surface=page.locator(`[data-interface-variant-group="${group}"]`);for(let i=1;i<position;i++)await surface.press('ArrowRight');await page.locator('.efhc-interface-customization-button').click()};
  await open(page);await choose('PB',24);
  await page.locator('a[href$="/referrals/"],a[href$="/referrals"]').first().click();await page.waitForSelector('[data-interface-variant-group="RP"]');await choose('RP',19);
  const saved=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')).interface_variants);
  assert.equal(saved.PB,'PB-20');assert.equal(saved.RP,'RP-06');
  await page.reload();await page.waitForFunction(()=>document.querySelector('[data-interface-variant-group="RP"]')?.dataset.pb==='PB-06');
  await page.locator(`a[href="${basePath}/"],a[href="${basePath}"]`).first().click();await page.waitForFunction(()=>document.querySelector('[data-interface-variant-group="PB"]')?.dataset.pb==='PB-22');
  await page.reload();await page.waitForFunction(()=>document.querySelector('[data-interface-variant-group="PB"]')?.dataset.pb==='PB-22');
 });
 for(const lang of ['en','ru','uk','de','fr','es','it','tr','pl','da','hi','id','sw','pt','ko','ja'])await check(`Energy uses rendered kWh casing in ${lang}`,async page=>{
  await open(page);
  const labels=page.locator('.efhc-energy-stage_subtitle,.efhc-energy-stage_range-center,[data-energy-chip="generation-rate"] > span,[data-energy-chip="available-kwh"] > span');
  let count=0;
  for(const label of await labels.all()){
   const units=(await label.innerText()).match(/kwh/gi)||[];
   for(const unit of units){assert.equal(unit,'kWh','CSS or translation changed the physical unit casing');count++;}
  }
  assert.ok(count>=3,'Energy units missing');
  assert.match(await page.locator('[data-energy-chip="generation-rate"] > span').innerText(),/kWh\/s$/,'rate unit must be identical in every language and retain lowercase Latin s');
 },{settings:{lang}});
 for(const [route,group] of [['','PB'],['referrals/','RP']])await check(`${group} first ten positions follow CT order without synchronizing manual choices`,async page=>{
  await open(page,route);await page.mouse.move(12,12);
  await page.locator('.efhc-interface-customization-button').click();
  const surface=page.locator(`[data-interface-variant-group="${group}"]`);
  const order=expectedSelectionOrder(group,canon);
  const count=order.length;
  const dots=page.locator('.efhc-interface-variant-dots').filter({has:page.locator(`:scope > span:nth-child(${count})`)});
  for(let i=0;i<10;i++){
   const selected=order[i],physical=canon.SOURCE_STYLE[group][selected]||selected;
   assert.equal(await surface.getAttribute('data-pb'),physical);
   await page.waitForFunction(({i,count})=>{const row=[...document.querySelectorAll('.efhc-interface-variant-dots')].find(e=>e.children.length===count);return row&&[...row.children].findIndex(e=>e.dataset.active==='true')===i},{i,count});
   assert.equal(await dots.locator('> span').count(),count);
   if(i<9)await surface.press('ArrowRight');
  }
  await page.locator('.efhc-interface-customization-button').click();
  await page.reload();await page.waitForFunction(({group,physical})=>document.querySelector(`[data-interface-variant-group="${group}"]`)?.dataset.pb===physical,{group,physical:canon.SOURCE_STYLE[group][order[9]]});
  assert.equal(await page.locator(`[data-interface-variant-group="${group}"]`).getAttribute('data-pb'),canon.SOURCE_STYLE[group][order[9]]);
  const saved=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')).interface_variants);
  assert.equal(saved[group],order[9]);
  assert.equal(saved[group==='PB'?'RP':'PB'],group==='PB'?'RP-01':'PB-01');
 });
 await check('Energy Lvl has the final HTML plain-text material in all ten themes',async page=>{
  await open(page);
  await page.mouse.move(12,12);
  await page.locator('.efhc-interface-customization-button').click();
  for(let i=0;i<10;i++){
   const actual=await page.locator('.efhc-energy-stage_level strong').evaluate(el=>{
    const s=getComputedStyle(el);return {text:el.textContent,background:s.backgroundColor,image:s.backgroundImage,borders:[s.borderTopWidth,s.borderRightWidth,s.borderBottomWidth,s.borderLeftWidth],shadow:s.boxShadow,color:s.color};
   });
   assert.match(actual.text,/Lvl\s*\d+/);
   assert.equal(actual.background,'rgba(0, 0, 0, 0)');
   assert.equal(actual.image,'none');
   assert.deepEqual(actual.borders,['0px','0px','0px','0px']);
   assert.equal(actual.shadow,'none');
   assert.equal(actual.color,'rgb(248, 250, 252)');
   await page.locator('[data-color-theme-control="true"]').click();
  }
 });
 for(const width of [320,390,1440]) await check(`PB-04 source segments and bounded height on both pages at ${width}px`,async page=>{
  // Expected material comes from immutable source CSS, not the candidate adapter.
  const css=await fs.readFile(new URL('../../public/FRONTEND_v866.css',import.meta.url),'utf8');
  const reference=await browser.newPage({viewport:{width,height:844}});
  let expected;
  try{
   await reference.setContent(`<style>${css}</style><div class="efhc-independent-shell" data-interface-app-mode="user"><section class="efhc-energy-stage"><div class="efhc-energy-progress-track" data-pb="PB-04"><div class="efhc-energy-progress-fill"></div></div></section></div>`);
   expected=await reference.locator('.efhc-energy-progress-fill').evaluate(el=>{const s=getComputedStyle(el);return {background:s.backgroundImage,color:s.backgroundColor,shadow:s.boxShadow}});
   assert.match(expected.background,/repeating-linear-gradient/,'source fixture lost authored segments');
  }finally{await reference.close()}
  for(const [route,group] of [['','PB'],['referrals/','RP']]){
   await open(page,route);
   await page.mouse.move(12,12);
   await page.locator('.efhc-interface-customization-button').click();
   const surface=page.locator(`[data-interface-variant-group="${group}"]`);
   // Actual keyboard selection, not direct data-pb mutation.
   const target=expectedSelectionOrder(group,canon).indexOf(`${group}-04`);
   for(let i=0;i<target;i++)await surface.press('ArrowRight');
   await page.waitForFunction(group=>document.querySelector(`[data-interface-variant-group="${group}"]`)?.dataset.pb==='PB-04',group);
   const actual=await surface.locator('.efhc-energy-progress-track').evaluate(el=>{
    const fill=el.querySelector('.efhc-energy-progress-fill'),s=getComputedStyle(fill),r=el.getBoundingClientRect(),f=fill.getBoundingClientRect();
    return {background:s.backgroundImage,color:s.backgroundColor,shadow:s.boxShadow,height:r.height,fillHeight:f.height,rootFont:parseFloat(getComputedStyle(document.documentElement).fontSize)};
   });
   assert.deepEqual({background:actual.background,color:actual.color,shadow:actual.shadow},expected,`${group} lost HTML PB-04 material`);
   const canonicalHeight=.715*actual.rootFont;
   assert.ok(actual.height>=canonicalHeight*.85&&actual.height<=canonicalHeight*1.15,`${group}: height ${actual.height} outside OWNER bounds around ${canonicalHeight}`);
   assert.ok(actual.fillHeight>0&&actual.fillHeight<=actual.height,`${group}: fill escapes track`);
   await page.locator('.efhc-interface-customization-button').click();
   const saved=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')).interface_variants);
   assert.equal(saved[group],`${group}-04`);
   assert.equal(saved[group==='PB'?'RP':'PB'],group==='PB'?'RP-01':'PB-04','manual selection changed the other page');
   if(process.env.EFHC_PARITY_ARTIFACTS){
    await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});
    await surface.screenshot({path:`${process.env.EFHC_PARITY_ARTIFACTS}/pb04-${group}-${width}.png`});
   }
  }
 },{width});
 await check('Admin exit does not retain the Admin renderer',async page=>{
  await open(page,'admin/');await page.waitForSelector('[data-admin-visual-proof-route="/admin"]');
  await page.locator('.efhc-game-header_profile-name-button').click();
  await page.waitForURL('**/web-profile/**');
  await page.waitForFunction(()=>!document.querySelector('[data-admin-visual-proof-route]'),null,{timeout:2500});
  assert.ok(await page.locator('[data-public-surface="profile"],.efhc-profile-page').count());
 });
 await check('Admin has an explicit functional exit',async page=>{
  await open(page,'admin/');await page.locator('[data-app-navigation="exit-admin"]').click();
  await page.waitForFunction(()=>document.querySelector('.efhc-energy-stage'));
  assert.equal(await routePath(page),'/');
  assert.equal(await page.locator('[data-admin-visual-proof-route]').count(),0);
 });
 for(const width of [390,430,768,1440])await check(`Admin width is stable before and after interaction ${width}`,async page=>{
  await open(page,'admin/');
  const samples=[];
  for(let i=0;i<3;i++){
   samples.push(await page.locator('.efhc-independent-shell').boundingBox());
   // A viewport coordinate can land on a navigation button after legitimate
   // Admin actions are added. Interact with the declared non-navigating target.
   if(i===0)await page.locator('.efhc-admin-header h1').click();
   await page.waitForTimeout(80);
   assert.equal(await routePath(page),'/admin','width interaction must remain on Admin');
  }
  for(const box of samples)assert.ok(Math.abs(box.width-width)<1,JSON.stringify(samples));
  const title=await page.locator('.efhc-admin-header h1').boundingBox();
  const actions=await page.locator('.efhc-admin-header .efhc-admin-actions').boundingBox();
  assert.ok(title&&actions&&(title.y+title.height<=actions.y+1||actions.y+actions.height<=title.y+1||title.x+title.width<=actions.x+1||actions.x+actions.width<=title.x+1),'Admin title overlaps its actions');
 },{width});
 for(const width of [360,430,768,1440])await check(`gear anchored to shell corner ${width}`,async page=>{
  await open(page);
  for(const editing of [false,true]){
   if(editing)await page.locator('.efhc-interface-customization-button').click();
   const geometry=await page.evaluate(()=>{const shell=document.querySelector('.efhc-independent-shell').getBoundingClientRect(),gear=document.querySelector('.efhc-interface-customization-button').getBoundingClientRect(),nav=document.querySelector('.efhc-game-nav').getBoundingClientRect();return{gap:shell.right-gear.right,bottom:nav.top-gear.bottom}});
   assert.ok(geometry.gap>=8&&geometry.gap<=12,JSON.stringify(geometry));
   assert.ok(geometry.bottom>=7&&geometry.bottom<=12,JSON.stringify(geometry));
  }
 },{width});
 await check('splash logo scales with the viewport',async page=>{
  await page.route('**/locale/**',async r=>{await new Promise(resolve=>setTimeout(resolve,700));await r.continue()});
  await page.goto(base,{waitUntil:'domcontentloaded'});
  const image=page.locator('.efhc-splash-breathe');await image.waitFor({state:'attached'});
  const box=await image.boundingBox();assert.ok(box&&box.width>=390*.7&&box.width<=390*.85,JSON.stringify(box));
 });
 await check('nested Energy progress selects PB rather than its parent EG',async page=>{
  await open(page);await page.locator('.efhc-interface-customization-button').click();
  const progress=page.locator('[data-interface-variant-group="PB"]').first();
  await progress.click();await page.waitForTimeout(150);
  const selected=expectedSelectionOrder('PB',canon)[1];
  assert.equal(await progress.getAttribute('data-pb'),canon.SOURCE_STYLE.PB[selected]||selected);
 });
 await check('readonly nested exchange stats still allow the parent XH template gesture',async page=>{
  await open(page,'exchange/');await page.locator('.efhc-interface-customization-button').click();
  await page.locator('.efhc-exchange-stats-surface .efhc-game-stat').first().click();
  assert.equal(await page.locator('.efhc-exchange-hero').getAttribute('data-xh'),'XH-02');
 });
 await check('rank selection KG-03 uses the authored KG-04 style',async page=>{
  await open(page,'ranks/');assert.equal(await page.locator('.efhc-ranks-shell').getAttribute('data-kg'),'KG-04');
 },{settings:{interface_variants:{...canon.DEFAULTS,KG:'KG-03'}}});
 await check('Android Back cancels template selection before leaving the page',async page=>{
  await open(page);await page.locator('.efhc-interface-customization-button').click();
  await page.evaluate(()=>window.__EFHC_ANDROID_BACK__());
  await page.waitForFunction(()=>document.querySelector('.efhc-independent-shell').dataset.interfaceCustomizationMode==='idle',null,{timeout:2500});
  assert.equal(await routePath(page),'/');
 });
 await check('Android Back leaves a directly opened Admin child and then Admin',async page=>{
  await open(page,'admin/users/');
  await page.evaluate(()=>window.__EFHC_ANDROID_BACK__());
  await page.waitForFunction(prefix=>location.pathname===prefix+'/admin/',basePath);
  await page.evaluate(()=>window.__EFHC_ANDROID_BACK__());
  await page.waitForFunction(prefix=>location.pathname===prefix+'/' && !document.querySelector('[data-admin-visual-proof-route]'),basePath);
  await page.waitForSelector('.efhc-energy-stage');
 });
 await check('Telegram Android Back is connected on Admin',async page=>{
  await open(page,'admin/users/');await page.evaluate(()=>window.__efhcHostTest.back());
  await page.waitForFunction(prefix=>location.pathname===prefix+'/admin/',basePath);
 },{telegram:true});
 await check('Android Back at the app root closes the Telegram host',async page=>{
  await open(page);await page.evaluate(()=>window.__EFHC_ANDROID_BACK__());
  assert.equal(await page.evaluate(()=>window.__efhcHostTest.closed),1);
 },{telegram:true});
 await check('browser Android Back closes the root dialog without leaving EFHC',async page=>{
  await open(page);await page.locator('[data-action="Deposit"]').click();
  await page.waitForSelector('[role="dialog"][aria-modal="true"]');await page.waitForTimeout(80);
  await page.evaluate(()=>history.back());await page.waitForTimeout(250);
  assert.ok(page.url().startsWith(base),'root dialog Back left the application');
  assert.equal(await page.locator('[role="dialog"][aria-modal="true"]').count(),0);
  assert.equal(await routePath(page),'/');
 });
 await check('browser Back cancels Admin editing without changing its URL',async page=>{
  await open(page);await page.locator('.efhc-game-header_profile-name-button').click();
  await page.waitForSelector('.efhc-profile-topbar');
  await page.locator('.efhc-profile-topbar_actions button').first().click();
  await page.waitForSelector('[data-admin-visual-proof-route]');
  await page.locator('.efhc-interface-customization-button').click();await page.waitForTimeout(80);
  await page.evaluate(()=>history.back());await page.waitForTimeout(250);
  assert.equal(await routePath(page),'/admin');
  assert.equal(await page.locator('.efhc-independent-shell').getAttribute('data-interface-customization-mode'),'idle');
 });
 await check('browser Back closes profile settings and preserves the profile URL',async page=>{
  await open(page);await page.locator('.efhc-game-header_profile-name-button').click();
  await page.waitForSelector('.efhc-profile-avatar-button');await page.locator('.efhc-profile-avatar-button').click();
  await page.waitForSelector('[role="dialog"][aria-modal="true"]');await page.waitForTimeout(80);
  await page.evaluate(()=>history.back());await page.waitForTimeout(250);
  assert.equal(await routePath(page),'/web-profile');
  assert.equal(await page.locator('[role="dialog"][aria-modal="true"]').count(),0);
 });
 await check('OWNER: gear auto-hides only in idle, returns on activity, save remains visible',async page=>{
  await open(page);
  const gear=page.locator('.efhc-interface-customization-button');
  assert.equal(await gear.getAttribute('data-visible'),'true','gear is not initially visible');
  await page.waitForTimeout(3250);
  assert.equal(await gear.getAttribute('data-visible'),'false','gear must hide after idle timeout');
  assert.equal(await gear.evaluate(el=>getComputedStyle(el).pointerEvents),'none','hidden gear intercepts taps');
  await page.mouse.move(12,12);
  await page.waitForFunction(()=>document.querySelector('.efhc-interface-customization-button')?.dataset.visible==='true');
  await page.waitForTimeout(3250);
  assert.equal(await gear.getAttribute('data-visible'),'false','gear did not reset hide timer');
  await page.evaluate(()=>window.dispatchEvent(new Event('touchstart')));
  await page.waitForFunction(()=>document.querySelector('.efhc-interface-customization-button')?.dataset.visible==='true');
  await gear.click();
  await page.waitForFunction(()=>document.querySelector('.efhc-independent-shell')?.dataset.interfaceCustomizationMode==='editing');
  await page.waitForTimeout(3250);
  assert.equal(await gear.getAttribute('data-visible'),'true','editing save button auto-hid');
  assert.equal(await gear.getAttribute('aria-label'),'Сохранить оформление');
  assert.equal(await page.locator('[data-color-theme-control="true"]').isVisible(),true,'globe vanished with gear');
 });
 await check('OWNER: globe is always visible during editing and cycles all 10 color themes',async page=>{
  await open(page);await page.clock.install();
  await page.locator('.efhc-interface-customization-button').click();
  const selector=page.locator('[data-color-theme-control="true"]');
  await selector.waitFor({state:'visible'});
  await page.clock.runFor(3500);
  assert.equal(await selector.isVisible(),true,'globe must not hide after three seconds');
  await page.mouse.move(12,12);
  await page.clock.runFor(3500);
  assert.equal(await selector.isVisible(),true,'globe must not hide after pointer activity or another timeout');
  for(let n=2;n<=11;n++){
    await selector.click();
    const expected='CT-'+String(n===11?1:n).padStart(2,'0');
    await page.waitForFunction(id=>document.documentElement.dataset.colorThemeId===id,expected);
    assert.equal(await selector.isVisible(),true,'globe vanished during ten-theme cycling');
  }
  await page.clock.runFor(3100);
  assert.equal(await selector.isVisible(),true,'globe disappeared while editing');
  assert.equal(await page.locator('.efhc-interface-customization-button').isVisible(),true,'save must stay visible');
  await selector.click();
  await page.waitForFunction(()=>document.documentElement.dataset.colorThemeId==='CT-02');
  await page.locator('.efhc-interface-customization-button').click();
  assert.equal(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')).color_theme_id),'CT-02','save did not persist the theme');
  assert.equal(await selector.count(),0,'globe must be absent outside editing');
  // OWNER acceptance: the selection survives an actual route reload.
  await page.clock.resume();
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.documentElement.dataset.colorThemeId==='CT-02');
  assert.equal(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('EFHC_USER_SETTINGS_V1')).color_theme_id),'CT-02','saved selection must survive reload');
  assert.equal(await page.locator('[data-color-theme-control="true"]').count(),0,'globe must remain absent after reload outside editing');
 });

 for(const theme of Array.from({length:10},(_,i)=>`CT-${String(i+1).padStart(2,'0')}`))await check(`OWNER followup: Header backgrounds, Ranks theme coverage, upper dots and Referrals removal ${theme}`,async page=>{
  await verifyUiFollowup(page,{open,artifacts:process.env.EFHC_PARITY_ARTIFACTS,theme,width:390});
 },{settings:{color_theme_id:theme}});
 for(const width of [320,1440])await check(`OWNER followup responsive ${width}`,async page=>{
  await verifyUiFollowup(page,{open,artifacts:process.env.EFHC_PARITY_ARTIFACTS,theme:'CT-03',width});
 },{width,settings:{color_theme_id:'CT-03'}});

 for(const width of [320,390,1440])await check(`OWNER cycle0023: fixed CT/page indicators, all local dots and USER boundaries ${width}`,async page=>{
  await verifyIndicators(page,{open,canon,width,artifacts:process.env.EFHC_PARITY_ARTIFACTS});
 },{width});

 await check('OWNER cycle0024: PA-01 matches measured v866 breakpoint and preserves D8 in ten themes',async page=>{
  await verifyPanelsActivationReference(page,{open,artifacts:process.env.EFHC_PARITY_ARTIFACTS});
 });

 await check('OWNER cycle0024/02: PH positions2–6 match source anatomy; PH01 and Header preserved',async page=>{
  await verifyPanelsHeroTemplates(page,{open,canon,artifacts:process.env.EFHC_PARITY_ARTIFACTS});
 });
 for(const width of [320,390,1440])await check(`OWNER cycle0024/02: all Portfolio designs follow all10 CT in both tabs ${width}`,async page=>{
  await verifyPortfolioColors(page,{open,canon,width,artifacts:process.env.EFHC_PARITY_ARTIFACTS});
 },{width});

}finally{await browser.close()}
if(process.env.EFHC_PARITY_ARTIFACTS){await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});await fs.writeFile(process.env.EFHC_PARITY_ARTIFACTS+'/interaction-results.json',JSON.stringify({results},null,2)+'\n')}
if(results.some(r=>r.status==='FAIL'))process.exitCode=1;
