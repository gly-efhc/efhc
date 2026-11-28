import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const material=JSON.parse(await fs.readFile(new URL('./theme-indicator-material.json',import.meta.url)));
const technicalCopy=(await Promise.all(['ru','en','uk','de','fr','es','it','tr','pl','da','hi','id','sw','pt','ko','ja'].map(async lang=>JSON.parse(await fs.readFile(new URL(`../../../frontend/public/locale/${lang}.json`,import.meta.url)))))).flatMap(d=>['error.system_theme_note'].map(k=>d[k]).filter(Boolean));
export async function verifyIndicators(page,{open,width,artifacts}){
 const routes=['','panels/','panels/portfolio/','exchange/','tasks/','referrals/','referrals/my/','referrals/active/','referrals/inactive/','ranks/','web-profile/','hub/','faq/','withdraw/','ads/','404/','500/'];
 for(const route of routes){
  await open(page,route);
  assert.equal(await page.locator('[data-user-indicator-dock]').count(),0,'dock absent in idle');
  await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();await page.waitForTimeout(100);
  const dock=page.locator('[data-user-indicator-dock]');assert.equal(await dock.count(),1,route+' single dock');
  assert.equal(await page.locator('[data-indicator-group="HS"][data-indicator-placement="inside"]').count(),1,'Header dots inside its free top edge');
  assert.equal(await dock.locator('[data-color-theme-indicators]>span').count(),10);
  assert.equal(await dock.innerText(),'','no labels or counters');
  const text=await page.locator('body').innerText();
  for(const phrase of technicalCopy)assert.ok(!text.includes(phrase),'USER engineering copy is permanently excluded: '+route);
  const exposed=await page.locator('[aria-label],[title]').evaluateAll(es=>es.flatMap(e=>[e.getAttribute('aria-label')||'',e.getAttribute('title')||'']).join('\n'));
  assert.doesNotMatch(exposed,/\b(?:HS|HB|BN|EG|EI|PH|PA|PT|PC|PB|RP|XH|XS|XC|XA|TG|RG|KG|WG|PM|HI|HU|FQ|WD|AD|ER)-\d{2}\b/,'internal design IDs belong in data attributes, not accessible copy');
  assert.equal(await page.locator('.efhc-energy-stage [data-color-theme-indicators]').count(),0,'no duplicate Energy indicator');
  const hr=await page.locator('.efhc-game-header').boundingBox(),dr=await dock.boundingBox();assert.ok(dr.y>=hr.y+hr.height-1,'dock under Header');
  assert.equal(await dock.evaluate(e=>e.closest('main')),null,'dock outside scrolling main');
  await page.locator('#efhc-main-content').evaluate(e=>{e.scrollTop=80});await page.waitForTimeout(100);
  const after=await dock.boundingBox();assert.ok(Math.abs(after.y-dr.y)<1,'dock fixed with Header');
  await page.locator('#efhc-main-content').evaluate(e=>{e.scrollTop=0});await page.waitForTimeout(100);
  for(const group of ['PB','RP']){
   const surface=page.locator(`[data-interface-variant-group="${group}"]`);if(!await surface.count())continue;
   const track=surface.locator('.efhc-energy-progress-track');await track.scrollIntoViewIfNeeded();await page.waitForTimeout(100);
   const dots=page.locator(`[data-indicator-group="${group}"]`);assert.equal(await dots.count(),1,group+' indicator visible');
   assert.equal(await dots.locator('span').count(),24,group+' all positions retained');assert.equal(await dots.locator('[data-active="true"]').count(),1);
   const tr=await track.boundingBox(),br=await dots.boundingBox();assert.ok(br.y>=tr.y+tr.height,'dots below track');assert.ok(br.y+br.height<=tr.y+tr.height+10,'dots directly below track, not below metrics');
   const id=await surface.getAttribute('data-pb');await surface.press('ArrowRight');await page.waitForTimeout(60);assert.notEqual(await surface.getAttribute('data-pb'),id,'selection works');assert.equal(await dots.locator('span').count(),24);
  }
  const overlaps=await page.locator('.efhc-interface-variant-dots[data-indicator-group]').evaluateAll(es=>{
   const bad=[],hit=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
   for(const dots of es){
    if(dots.dataset.indicatorPlacement==='page')continue;
    const r=dots.getBoundingClientRect(),walker=document.createTreeWalker(document.querySelector('.efhc-independent-shell'),NodeFilter.SHOW_TEXT);let n;
    while((n=walker.nextNode())){if(!n.textContent.trim()||n.parentElement.closest('[aria-hidden="true"],script,style'))continue;const main=n.parentElement.closest('main');if(main&&!hit(r,main.getBoundingClientRect()))continue;let box=n.parentElement.getBoundingClientRect();if(!hit(r,box))continue;let range=document.createRange();range.selectNodeContents(n);if([...range.getClientRects()].some(b=>hit(r,b)))bad.push(dots.dataset.indicatorGroup+': '+n.textContent.trim().slice(0,40))}
   }return bad;
  });assert.deepEqual(overlaps,[],route+' dots cover no text');
  if(artifacts&&['','referrals/','ranks/','panels/portfolio/'].includes(route))await page.screenshot({path:`${artifacts}/indicators-${route.replaceAll('/','-')||'energy'}-${width}.png`});
  await page.locator('.efhc-interface-customization-button').click();assert.equal(await dock.count(),0,'dock removed on save');
 }
 await open(page);await page.mouse.move(12,12);await page.locator('.efhc-interface-customization-button').click();
 for(let i=1;i<=10;i++){
  const theme='CT-'+String(i).padStart(2,'0');await page.waitForFunction(id=>document.documentElement.dataset.colorThemeId===id,theme);
  const colors=await page.locator('[data-user-indicator-dock] [data-color-theme-indicators]>span').evaluateAll(es=>es.map(e=>{let s=getComputedStyle(e);return{id:e.dataset.colorThemeId,active:e.dataset.active,background:s.backgroundColor,border:s.borderColor,opacity:s.opacity,shadow:s.boxShadow}}));
  assert.deepEqual(colors,material.themes[theme],theme+' original dim theme colors preserved');await page.locator('[data-color-theme-control]').click();
 }
 await page.locator('.efhc-interface-customization-button').click();
 const appRoot=page.url();
 for(const route of ['admin/','browser-shop/']){
  await page.goto(new URL(route,appRoot).href,{waitUntil:'domcontentloaded'});await page.waitForTimeout(500);
  assert.equal(await page.locator('[data-user-indicator-dock]').count(),0,'independent renderer '+route);
 }
}
