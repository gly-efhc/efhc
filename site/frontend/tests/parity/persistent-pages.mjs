/**
 * Mandatory Pages smoke against the actual server-rendered React static export.
 *
 * No browser finance fixtures or obsolete v893 scenario store. Intercept external
 * traffic to emulate unavailable DEMO API. Page structure and navigation must
 * remain visible while requests fail. Historical visual parity checks are kept
 * available under EFHC_PERSISTENCE_FULL=1, not silently deleted.
 */
import {localPagesBase} from './pages-base.mjs';
import {verifyPortfolioThemeHeights} from './portfolio-theme-height.mjs';
import {verifyHeaderMaterials} from './header-material.mjs';
import {verifyStaticPages,staticRoutes} from './static-pages.mjs';
import {verifyTasksData} from './tasks-data.mjs';
import {verifyFrameThickness,verifyVisibleHeroFrames} from './frame-thickness.mjs';
import {verifyColorThemePages} from './color-theme-pages.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.env.EFHC_BROWSER_TOOLS||import.meta.url)('playwright-core');
const base=localPagesBase();
const dir=process.env.EFHC_PARITY_ARTIFACTS||'/tmp/efhc-persistence-artifacts';
await fs.mkdir(dir,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
const context=await browser.newContext({viewport:{width:390,height:844}});
const page=await context.newPage();
page.setDefaultTimeout(12000);
const ownOrigin=new URL(base).origin;
await context.route('**/*',route=>{
  const url=route.request().url();
  return new URL(url).origin===ownOrigin ? route.continue() : route.abort();
});
const errors=[],results=[];
page.on('pageerror',error=>errors.push({url:page.url(),message:error.message}));
async function check(name,fn){
  if(process.env.EFHC_PERSISTENCE_FOCUS&&!name.includes(process.env.EFHC_PERSISTENCE_FOCUS))return;
  try{await fn();results.push({name,status:'PASS'});console.log('PASS '+name);}
  catch(error){
    results.push({name,status:'FAIL',error:String(error?.message||error)});
    console.error('FAIL '+name+': '+String(error?.message||error),JSON.stringify({actual:error?.actual,expected:error?.expected,url:page.url()}));
    await page.screenshot({path:dir+'/persistent-failure-'+results.length+'.png',fullPage:true}).catch(()=>undefined);
  }
}
async function visit(route=''){
  await page.goto(base+route,{waitUntil:'domcontentloaded',timeout:20000});
  await page.locator('body').waitFor({state:'visible'});
}
async function assertUserShell(){
  const main=page.locator('#efhc-main-content');
  await main.waitFor({state:'visible'});
  await page.locator('.efhc-game-nav').waitFor({state:'visible'});
  assert.equal(await page.locator('.efhc-game-nav a').count(),6,'six fixed navigation destinations');
  if (await page.locator('[data-public-surface="hub"]').count()) {
    assert.equal(await page.locator('[data-hub-link-slot-grid]').count(),1,'persistent authorized HUB grid');
  } else assert.ok((await main.innerText()).trim().length>10,'persistent page content');
  assert.ok(!/Application error|ZodError/.test(await page.locator('body').innerText()));
  assert.equal(await page.locator('[data-energy-state="loading"],[data-energy-state="recoverable-error"]').count(),0);
}
const userRoutes=['','panels/','exchange/','referrals/','tasks/','ranks/','hub/','web-profile/','faq/'];
try{
  await check('Tasks keeps its own interface after valid and malformed data arrive',async()=>{
    const cases=await verifyTasksData({base,artifacts:dir});
    assert.equal(cases.length,6);
  });
  await check('every static route retains controls through auth and API failures',async()=>{
    const matrix=await verifyStaticPages({base,artifacts:dir,widths:[390,1440],modes:['offline','slow','401','403','500','malformed']});
    assert.ok(!staticRoutes.includes('dev/neon'),'retired TEST route must not be exported');
    assert.equal(matrix.length,2*(staticRoutes.length+5*7),'full static route and failure-mode matrix');
  });
  for(const route of userRoutes)await check('offline keeps USER page '+(route||'home'),async()=>{
    await visit(route);
    await assertUserShell();
    if(!route){
      await page.locator('.efhc-energy-stage').waitFor({state:'visible'});
      assert.equal(await page.locator('[data-energy-chip]').count(),3);
      assert.equal(await page.locator('.efhc-energy-progress-track').count(),1);
    }
  });
  await check('browser Back and Forward keep their final requested routes',async()=>{
    await visit();
    const hrefs=await page.locator('.efhc-game-nav a').evaluateAll(as=>as.map(a=>a.getAttribute('href')));
    const referrals=hrefs.find(href=>/\/referrals\/?$/.test(href));
    const ranks=hrefs.find(href=>/\/ranks\/?$/.test(href));
    assert.ok(referrals&&ranks);
    for(const href of [referrals,ranks]){
      await page.locator(`.efhc-game-nav a[href="${href}"]`).click();
      await page.waitForURL(new URL(href,base).href);
      await page.waitForTimeout(300);
    }
    await page.goBack();
    await page.waitForURL(new URL(referrals,base).href);
    await page.waitForTimeout(300);
    assert.equal(page.url(),new URL(referrals,base).href,'Back must remain on Referrals');
    await page.goForward();
    await page.waitForURL(new URL(ranks,base).href);
    await page.waitForTimeout(300);
    assert.equal(page.url(),new URL(ranks,base).href,'Forward must remain on Ranks after all handlers');
    await assertUserShell();
  });
  await check('retired public TEST console exposes no operator credentials or top-up controls',async()=>{
    await visit('dev/neon/');
    const body=await page.locator('body').innerText();
    assert.equal(await page.getByPlaceholder('Пароль TEST оператора').count(),0);
    assert.ok(!body.includes('DEMO backend / Neon TEST'));
    assert.ok(!body.includes('Тестовое пополнение через банк'));
    assert.ok(!body.includes('Временный ключ просмотра Admin'));
  });
  await check('offline Admin remains private before server-attested key login',async()=>{
    await visit('admin/');
    // Owner policy: neither a public Pages flag nor offline cache is proof
    // of Admin authorization. Fail closed while the real API is unavailable.
    await page.locator('[data-admin-access="denied"]').waitFor({state:'visible'});
    const pathname=new URL(page.url()).pathname;
    assert.ok(pathname.endsWith('/admin/')||pathname.endsWith('/admin'),
      'Admin deep link should remain addressable without exposing the page');
    assert.equal(await page.locator('[data-admin-primitive="page"]').count(),0,
      'Anonymous/offline user must never receive Admin UI');
    assert.equal(await page.locator('[data-app-navigation="exit-admin"]').count(),0,
      'Anonymous/offline user must never see Admin navigation');
    assert.ok((await page.locator('body').innerText()).includes('Доступ'));
  });
  await check('Browser Shop remains a full local page without external requests',async()=>{
    await visit('browser-shop/');
    await page.locator('[data-public-surface="browser-shop"]').waitFor({state:'visible'});
    assert.ok((await page.locator('body').innerText()).trim().length>25);
  });
  await check('one-pixel visible frames on real React Pages in USER Admin and Shop',async()=>{
    const cases=await verifyFrameThickness(page,{base});
    assert.ok(cases.length>=14,'expected frame matrix across ten color themes');
  });
  await check('all mounted Hero contours stay visibly colored and one pixel across ten CT',async()=>{
    const rows=await verifyVisibleHeroFrames(page,{base});
    assert.equal(rows.length,40,'4 live route heroes x 10 color themes');
  });
  await check('all USER routes keep Theme03 material roles and geometry across ten CT and two widths',async()=>{
    const rows=await verifyColorThemePages(page,{base,artifacts:dir});
    assert.ok(rows.length>=30,'expected every USER route at mobile and desktop');
    assert.ok(rows.every(row=>row.themes===10),'ten themes required for each route');
  });
  await check('removed browser finance store does not reappear',async()=>{
    await visit();
    assert.equal(await page.evaluate(()=>localStorage.getItem('efhc:react:unified-demo:v893')),null);
  });
  if(process.env.EFHC_PERSISTENCE_FULL==='1'){
    await check('protected Portfolio CT04 geometry in all ten themes',async()=>{
      await verifyPortfolioThemeHeights(page,{base,artifacts:dir});
    });
    await check('protected Header materials in six designs across themes',async()=>{
      const cases=await verifyHeaderMaterials(page,{base,artifacts:dir});
      assert.equal(cases.length,124);
    });
  }
  await check('no unhandled React or hydration exceptions',async()=>{
    assert.deepEqual(errors,[]);
  });
}finally{
  await fs.writeFile(dir+'/persistent-pages.json',JSON.stringify({base,results,errors,full:process.env.EFHC_PERSISTENCE_FULL==='1'},null,2));
  await context.unrouteAll({behavior:'ignoreErrors'});
  await browser.close();
}
if(results.some(item=>item.status==='FAIL'))process.exitCode=1;
