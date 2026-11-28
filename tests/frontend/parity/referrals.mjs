import {localPagesBase} from './pages-base.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(process.env.EFHC_BROWSER_TOOLS||new URL('../../../frontend/package.json',import.meta.url)),{chromium}=require('playwright-core');
const canon=JSON.parse(await fs.readFile(new URL('./source-interface-contract.json',import.meta.url)));
const reference=JSON.parse(await fs.readFile(new URL('./referrals-text-reference.json',import.meta.url)));
assert.equal(reference.source_html_sha256,canon.source_html_sha256||'9b6371f5fb62939596b78206f95031c447e9f2b375e62b30704403bb25102aef');
const base=localPagesBase();
const basePath=new URL(base).pathname.replace(/\/$/,'');
const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
const page=await browser.newPage({viewport:{width:390,height:844}}),results=[];
await page.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
await page.addInitScript(defaults=>localStorage.setItem('EFHC_USER_SETTINGS_V1',JSON.stringify({lang:'ru',interface_settings_version:4,color_theme_id:'CT-01',interface_variants:defaults,music_enabled:false})),canon.DEFAULTS);
try{
 await page.goto(base+'referrals/');await page.waitForSelector('[data-public-surface="referrals"]');await page.waitForSelector('.efhc-entry-splash',{state:'hidden'});
 assert.equal(await page.locator('.efhc-referrals-shell .efhc-game-kicker').innerText(),'ПАРТНЁРСКАЯ СИСТЕМА');
 assert.ok((await page.locator('.efhc-referrals-shell').innerText()).includes('Уровни достижений'));
 assert.ok((await page.locator('.efhc-referrals-shell').innerText()).includes('Пригласить пользователя'));
 for(const width of [320,390,1440]){
  await page.setViewportSize({width,height:844});
  const rows=await page.evaluate(canon=>{
   const root=document.querySelector('[data-public-surface="referrals"]'),shell=root.closest('.efhc-independent-shell');
   const output=[];
   const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
   function rgba(value){ctx.clearRect(0,0,1,1);ctx.fillStyle=value;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data]}
   for(const theme of canon.COLOR_THEME_CATALOG){
    for(const n of [document.documentElement,shell]){n.dataset.colorThemeId=theme.id;n.dataset.globalThemeId=canon.COLOR_TO_RUNTIME_LEGACY_THEME[theme.id];}
    for(const variant of canon.REGISTRY.RG){
     root.dataset.rg=variant;
     const frame=getComputedStyle(root),hero=getComputedStyle(root.querySelector('.efhc-game-hero')),cards=[...root.querySelectorAll('.efhc-card')].map(e=>{const s=getComputedStyle(e);return[s.borderRadius,s.borderWidth,s.backgroundImage,s.backgroundColor,s.boxShadow,s.backdropFilter]}),rect=root.getBoundingClientRect();
     const brands=[...root.querySelectorAll('[data-referral-share-kind]')].map(e=>({kind:e.dataset.referralShareKind,color:getComputedStyle(e).backgroundColor}));
     const textColors={};
     for(const [role,selector] of Object.entries({kicker:'.efhc-game-kicker',title:'.efhc-game-title',detail:'.efhc-game-detail',statLabel:'.efhc-game-stat_label',statValue:'.efhc-game-stat_value',inviteDetail:'.efhc-text-muted2',cardTitle:'.efhc-card > .text-lg.font-semibold',caption:'.efhc-referral-achievement-caption'})){
      const n=root.querySelector(selector);if(!n)throw Error('Missing React role '+role);textColors[role]=rgba(getComputedStyle(n).color);
     }
     const materials={};for(const [role,selector] of Object.entries({root:'.efhc-referrals-shell',hero:'.efhc-game-hero',stat:'.efhc-game-stat',inviteCard:'.efhc-referrals-invite-card'})){const n=role==='root'?root:root.querySelector(selector),c=getComputedStyle(n);materials[role]={background:rgba(c.backgroundColor),image:c.backgroundImage,border:parseFloat(c.borderTopWidth)>0&&c.borderTopStyle!=='none'?rgba(c.borderTopColor):null}}

     output.push({theme:theme.id,variant,overflow:document.documentElement.scrollWidth>innerWidth+1,width:rect.width,signature:JSON.stringify([frame.borderRadius,frame.backgroundImage,frame.backgroundColor,hero.borderRadius,hero.borderWidth,hero.backgroundImage,hero.boxShadow,hero.backdropFilter,cards]),brands,textColors,materials});
    }
   }
   return output;
  },canon);
  const expected={telegram:'rgb(38, 165, 228)',whatsapp:'rgb(37, 211, 102)',viber:'rgb(115, 96, 242)',facebook:'rgb(8, 102, 255)',x:'rgb(17, 17, 17)'};
  for(const row of rows){assert.ok(!row.overflow,`referrals overflow ${width}/${row.variant}`);const expectedRow=reference.rows.find(x=>x.theme===row.theme&&x.variant===row.variant);assert.ok(expectedRow,'Missing immutable reference row');assert.deepEqual(row.textColors,expectedRow.colors,`canonical text colors ${width}/${row.theme}/${row.variant}`);assert.deepEqual(row.materials,expectedRow.materials,`canonical surface colors ${width}/${row.theme}/${row.variant}`);for(const b of row.brands)assert.equal(b.color,expected[b.kind],`brand color changed by ${row.theme}/${row.variant}`);}
  // Signatures are diagnostics only; fidelity is checked against independent HTML measurements.
  const signatures=new Set(rows.filter(x=>x.theme==='CT-01').map(x=>x.signature));
  results.push({width,status:'PASS',combinations:rows.length,signatures:signatures.size});console.log('PASS referrals',width,'combinations',rows.length,'signatures',signatures.size);
 }
 if(process.env.EFHC_PARITY_ARTIFACTS){await page.reload();await page.waitForSelector('.efhc-entry-splash',{state:'hidden'});await page.setViewportSize({width:390,height:844});await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});await page.screenshot({path:process.env.EFHC_PARITY_ARTIFACTS+'/referrals-restored-390.png',fullPage:true});}
}catch(e){results.push({status:'FAIL',error:e.message});console.error('FAIL referrals',e.message);process.exitCode=1}finally{await browser.close()}
if(process.env.EFHC_PARITY_ARTIFACTS){await fs.mkdir(process.env.EFHC_PARITY_ARTIFACTS,{recursive:true});await fs.writeFile(process.env.EFHC_PARITY_ARTIFACTS+'/referrals-results.json',JSON.stringify({results},null,2)+'\n')}
