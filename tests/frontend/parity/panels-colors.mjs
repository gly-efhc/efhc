import {localPagesBase} from './pages-base.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.env.EFHC_BROWSER_TOOLS||new URL('../../../frontend/package.json',import.meta.url))('playwright-core');
const base=localPagesBase(),canon=JSON.parse(await fs.readFile(new URL('./source-interface-contract.json',import.meta.url)));
const baseline=JSON.parse(await fs.readFile(new URL('./panels-material.json',import.meta.url)));
const directory=process.env.EFHC_PARITY_ARTIFACTS||'/tmp/efhc-panels-colors';await fs.mkdir(directory,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
const page=await browser.newPage({viewport:{width:390,height:844}}),results=[],errors=[];
await page.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(defaults=>{localStorage.setItem('EFHC_USER_SETTINGS_V1',JSON.stringify({lang:'ru',interface_settings_version:4,color_theme_id:'CT-01',interface_variants:{...defaults,PH:'PH-01',PA:'PA-01'},music_enabled:false}));},canon.DEFAULTS);
// Chromium serializes gradient alpha through 8-bit channels (e.g. .135 → .133).
const normalized=s=>s.replace(/rgba\((\d+), (\d+), (\d+), ([\d.]+)\)/g,(_,r,g,b,a)=>`rgba(${r}, ${g}, ${b}, ${Math.round(Number(a)*255)})`);
async function advance(group){await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();await page.locator(`[data-interface-variant-group="${group}"]`).press('ArrowRight');await page.locator('.efhc-interface-customization-button').click();await page.waitForTimeout(400);}
try{
 await page.goto(base+'panels/');await page.waitForSelector('[data-panel-activation-cta]');await page.waitForTimeout(1000);
 for(let ct=0;ct<10;ct++){
  for(let slot=0;slot<6;slot++){
   const actual=await page.evaluate(fields=>{
    const shell=document.querySelector('.efhc-independent-shell'),hero=document.querySelector('[data-panels-hero-source]'),card=document.querySelector('.efhc-panels-activation-card'),button=card.querySelector('[data-panel-activation-cta]');
    const styles=e=>Object.fromEntries(fields.map(k=>[k,getComputedStyle(e)[k]]));
    const s=getComputedStyle(button),rgb=getComputedStyle(shell).getPropertyValue('--efhc-ct-accent-rgb').split(',').map(Number);
    const rect=button.getBoundingClientRect(),parent=card.getBoundingClientRect();
    return {ct:shell.dataset.colorThemeId,ph:hero.dataset.ph,pa:card.dataset.pa,rgb,hero:styles(hero),activation:styles(card),button:{bg:s.backgroundColor,image:s.backgroundImage,border:s.borderTopColor,color:s.color,shadow:s.boxShadow,opacity:s.opacity},geometry:{height:rect.height,inside:rect.x>=parent.x&&rect.right<=parent.right+1},tier:[...document.querySelectorAll('.efhc-panels-generation-tier,.efhc-panels-generation-tier_dot')].map(e=>({dot:e.classList.contains('efhc-panels-generation-tier_dot'),shadow:getComputedStyle(e).boxShadow}))};
   },Object.keys(baseline.cases[0].hero));
   const previous=baseline.cases.find(x=>x.ct===actual.ct&&x.ph===actual.ph&&x.pa===actual.pa);assert.ok(previous,'physical template identity');
   const expectedHero={...previous.hero};
   // C31 authorizes only removing CT03's duplicate full inset contour.
   // PH03 has no physical border and retains its single inset contour.
   if(actual.ct==='CT-03'&&actual.ph!=='PH-03')expectedHero.boxShadow='rgba(0, 0, 0, 0.26) 0px 14px 34px 0px';
   assert.deepEqual(actual.hero,expectedHero,`${actual.ct}/${actual.ph} background and material preserved except the authorized duplicate contour`);
   assert.deepEqual(actual.activation,previous.activation,`${actual.ct}/${actual.pa} card background preserved`);
   const rgba=alpha=>`rgba(${actual.rgb.join(', ')}, ${alpha})`;
   const expected=actual.ct==='CT-03'?{bg:rgba(.065),image:'none',border:.42}:actual.ct==='CT-10'?{bg:rgba(.015),image:'none',border:.37}:actual.pa==='PA-04'?{bg:rgba(.065),image:'none',border:.35}:actual.pa==='PA-02'?{bg:'rgba(0, 0, 0, 0)',image:`linear-gradient(${rgba(.135)}, ${rgba(.095)})`,border:.38}:{bg:'rgba(0, 0, 0, 0)',image:`linear-gradient(${rgba(.1)}, ${rgba(.05)})`,border:.34};
   assert.equal(normalized(actual.button.bg),normalized(expected.bg));assert.equal(normalized(actual.button.image),normalized(expected.image));assert.equal(normalized(actual.button.border),normalized(rgba(expected.border)));
   assert.equal(actual.button.opacity,'1','only the background was made transparent');assert.ok(actual.geometry.height>=39&&actual.geometry.inside,'CTA geometry and tap area');
   if(actual.ct==='CT-03')assert.ok(normalized(actual.button.shadow).includes(normalized(rgba(.09))),'existing CTA glow reduced 10%');
   for(const tier of actual.tier)assert.ok(normalized(tier.shadow).includes(normalized(rgba(tier.dot ? .9 : .09))),'existing colored tier glow reduced 10%');
   results.push(actual);
   if(slot===0&&['CT-01','CT-03','CT-10'].includes(actual.ct))await page.screenshot({path:path.join(directory,`panels-${actual.ct}.png`),fullPage:true});
   await advance('PA');await advance('PH');
  }
  await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();await page.locator('[data-color-theme-control="true"]').click();await page.locator('.efhc-interface-customization-button').click();await page.waitForTimeout(400);
 }
 assert.equal(results.length,60);assert.equal(errors.length,0,errors.join('\n'));console.log('PANELS_COLORS=PASS 60 physical PH/PA × CT cases; background alpha ×0.5; external glow ×0.9; other materials unchanged');
}catch(error){await page.screenshot({path:path.join(directory,'panels-colors-failure.png'),fullPage:true});throw error;}
finally{await fs.writeFile(path.join(directory,'panels-colors.json'),JSON.stringify({results,errors},null,2));await browser.close();}
