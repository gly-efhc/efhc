import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const reference=JSON.parse(await fs.readFile(new URL('./header-material-reference.json',import.meta.url)));
const physical=['HS-03','HS-06','HS-07','HS-10','HS-11','HS-13'];
const accents=[[110,168,255],[115,174,252],[167,139,250],[34,158,217],[229,191,88],[217,70,239],[127,180,255],[143,134,255],[88,199,180],[197,161,90]];
// Chromium may serialize equivalent colors as rgba() or color(srgb ...).
const normalize=value=>value.replace(/color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?\)/g,(_,r,g,b,a='1')=>`rgba(${[r,g,b].map(n=>Math.round(Number(n)*255)).join(', ')}, ${a})`)
 .replace(/rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)/g,(_,r,g,b,a='1')=>`color(${r},${g},${b},${Math.round(Number(a)*255)})`);
const recolor=(value,rgb)=>value.replace(/rgba\(167, 139, 250, ([\d.]+)\)/g,(_,a)=>`rgba(${rgb.join(', ')}, ${a})`)
 .replaceAll('rgb(167, 139, 250)',`rgb(${rgb.join(', ')})`)
 .replace(/color\(srgb 0\.654902 0\.545098 0\.980392 \/ ([\d.]+)\)/g,(_,a)=>`rgba(${rgb.join(', ')}, ${a})`);
function readMaterials(selectors){
 return Object.fromEntries(selectors.map(selector=>{const s=getComputedStyle(document.querySelector(selector));return [selector,{background:s.background,borderColor:s.borderColor,color:s.color,boxShadow:s.boxShadow}];}));
}
function compareMaterials(actual,hs,rgb,label){
 const source=reference.cases.find(x=>x.hs===hs);assert.ok(source,hs);
 for(const [selector,properties] of Object.entries(source.parts))for(const [property,value] of Object.entries(properties)){
  assert.equal(normalize(actual[selector][property]),normalize(recolor(value,rgb)),`${label}: ${selector} ${property}`);
 }
}

function readProtectedContent(){
 const properties=['background','color','boxShadow','borderWidth','borderColor','borderRadius','fontFamily','fontSize','fontWeight','lineHeight','padding','margin','gap','display','gridTemplateColumns'];
 const main=document.querySelector('#efhc-main-content');assertMain(main);
 function assertMain(value){if(!value)throw Error('protected main content missing');}
 return [main,...main.querySelectorAll('*')].map(element=>{
  const style=getComputedStyle(element),rect=element.getBoundingClientRect();
  return {tag:element.tagName,text:element.children.length?null:element.textContent,
   rect:[rect.x,rect.y,rect.width,rect.height],style:Object.fromEntries(properties.map(p=>[p,style[p]]))};
 });
}

async function verifyProtectedContent(page,route){
 await page.clock.pauseAt(new Date(await page.evaluate(()=>Date.now()+250)));
 // JS clock control does not pause compositor width transitions. Settle only
 // visual motion during this two-state measurement; runtime CSS is untouched.
 const motion=await page.addStyleTag({content:'#efhc-main-content,#efhc-main-content *{transition:none!important;animation:none!important}'});
 const before=await page.evaluate(readProtectedContent);
 await page.evaluate(()=>{const link=document.querySelector('link[data-efhc-visual-adapter="header-material"]');if(!link?.sheet)throw Error('Header material delivery missing');link.sheet.disabled=true;});
 const original=await page.evaluate(readProtectedContent);
 assert.deepEqual(before,original,`${route}: enabling the Header contract must not alter protected main content, styles or geometry`);
 await page.evaluate(()=>{document.querySelector('link[data-efhc-visual-adapter="header-material"]').sheet.disabled=false;});
 await motion.evaluate(element=>element.remove());
 await page.clock.resume();return {route,elements:before.length};
}

export async function verifyHeaderMaterials(parentPage,{base,artifacts,widths=[320,1440]}={}){
 const context=await parentPage.context().browser().newContext(),page=await context.newPage(),results=[],protectedResults=[],errors=[];
 page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 await context.route('**/*',async route=>{
  if(new URL(route.request().url()).origin!==new URL(base).origin)return route.abort();
  return new URL(base).protocol==='https:'?route.fulfill({response:await route.fetch({maxRedirects:0})}):route.continue();
 });
 await context.addInitScript(()=>{
  if(!localStorage.getItem('EFHC_USER_SETTINGS_V1'))localStorage.setItem('EFHC_USER_SETTINGS_V1',JSON.stringify({interface_settings_version:4,lang:'ru',color_theme_id:'CT-01',interface_variants:{HS:'HS-01',PH:'PH-01'},music_enabled:false}));
 });
 await page.clock.install({time:new Date()});
 try{
  for(const width of widths){
   await page.setViewportSize({width,height:844});await page.goto(base+'panels/',{waitUntil:'domcontentloaded'});
   await page.locator('.efhc-entry-splash[aria-hidden="false"]').waitFor({state:'hidden',timeout:30000});
   await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();
   for(const hs of physical){
    assert.equal(await page.locator('.efhc-game-header').getAttribute('data-hs'),hs,'independent Header designs retain their identities/order');
    for(let color=1;color<=10;color++){
     const ct='CT-'+String(color).padStart(2,'0');await page.waitForFunction(ct=>document.documentElement.dataset.colorThemeId===ct,ct);
     const materials=await page.evaluate(readMaterials,Object.keys(reference.cases[0].parts));
     compareMaterials(materials,hs,accents[color-1],`${width}/${hs}/${ct}`);
     results.push({width,hs,ct,materials});
     await page.locator('[data-color-theme-control="true"]').click();
    }
    await page.locator('[data-interface-variant-group="HS"]').press('ArrowRight');
   }
   // The fixture's first launch is CT01: Admin must ignore that blue USER choice.
   await page.locator('.efhc-interface-customization-button').click();
   for(const route of ['admin/','admin/bank/']){
    await page.goto(base+route,{waitUntil:'domcontentloaded'});await page.locator('.efhc-game-header').waitFor();
    const hs=await page.locator('.efhc-game-header').getAttribute('data-hs');
    const materials=await page.evaluate(readMaterials,Object.keys(reference.cases[0].parts));
    compareMaterials(materials,hs,accents[2],`${width}/${route}/fixed CT03`);
    assert.equal(await page.locator('.efhc-independent-shell').getAttribute('data-color-theme-id'),null,'do not apply USER theme attributes to Admin content');
    results.push({width,route,hs,ct:'ADMIN_FIXED_CT03',materials});
   }
   for(const route of ['', 'panels/portfolio/', 'hub/', 'admin/bank/']){
    await page.goto(base+route,{waitUntil:'domcontentloaded'});
    await page.locator('.efhc-entry-splash[aria-hidden="false"]').waitFor({state:'hidden',timeout:30000});
    await page.locator('#efhc-main-content').waitFor();
    if(route==='panels/portfolio/')await page.locator('.efhc-panel-tile').first().waitFor();
    if(route==='admin/bank/')await page.locator('[data-bank-state="ready"]').waitFor({state:'attached'});
    protectedResults.push({width,...await verifyProtectedContent(page,route||'Energy')});
   }
  }
  assert.deepEqual(errors,[]);return results;
 }finally{
  if(artifacts){await fs.mkdir(artifacts,{recursive:true});await fs.writeFile(artifacts+'/header-material.json',JSON.stringify({reference:reference.source_head,results,protectedResults,errors},null,2));}
  await context.unrouteAll({behavior:'ignoreErrors'});await context.close();
 }
}
