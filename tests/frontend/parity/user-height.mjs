import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

export async function verifyUserHeight(page,{open,artifacts}) {
 const results=[];
 for(const viewport of [{width:320,height:568},{width:390,height:1000},{width:844,height:390}]){
  await page.setViewportSize(viewport);
  for(const route of ['', 'panels/', 'panels/portfolio/', 'exchange/', 'tasks/', 'referrals/', 'ranks/', 'hub/', 'faq/', 'web-profile/']){
   await open(page,route);
   await page.locator('.efhc-entry-splash').waitFor({state:'hidden',timeout:20000});
   const actual=await page.evaluate(()=>{
    const main=document.querySelector('#efhc-main-content'),nav=document.querySelector('.efhc-game-nav'),header=document.querySelector('.efhc-game-header');
    const box=e=>e.getBoundingClientRect().toJSON();
    main.scrollTop=main.scrollHeight;
    const root=main.querySelector(':scope > .efhc-game-page');
    return {main:box(main),nav:box(nav),header:box(header),mainScroll:main.scrollTop,contentHeight:main.clientHeight-parseFloat(getComputedStyle(main).paddingTop)-parseFloat(getComputedStyle(main).paddingBottom),pageHeight:root?.getBoundingClientRect().height,overflow:getComputedStyle(main).overflowY,documentWidth:document.documentElement.scrollWidth,viewport:innerWidth};
   });
   if(artifacts)await fs.writeFile(`${artifacts}/user-height-current.json`,JSON.stringify({viewport,route,actual},null,2)+'\n');
   assert.ok(actual.main.bottom<=actual.nav.top+1,`${route} main overlaps bottom nav: ${JSON.stringify(actual)}`);
   assert.ok(actual.main.top>=actual.header.bottom-1,`${route} main overlaps Header`);
   assert.ok(actual.documentWidth<=actual.viewport+1,`${route} horizontal overflow`);
   assert.equal(actual.overflow,'auto');
   if(route!=='panels/portfolio/' && actual.pageHeight!==undefined)assert.ok(actual.pageHeight>=actual.contentHeight-2,`${route} page container fails to fill free height`);
   // Scrolling content must not move the protected header/navigation.
   const anchored=await page.evaluate(()=>({header:document.querySelector('.efhc-game-header').getBoundingClientRect().top,nav:document.querySelector('.efhc-game-nav').getBoundingClientRect().top}));
   assert.ok(Math.abs(anchored.header-actual.header.top)<1 && Math.abs(anchored.nav-actual.nav.top)<1);
   results.push({viewport,route,status:'PASS',actual});
  }
 }
 // A taller viewport must enlarge the list viewport, not its panel tiles.
 await page.setViewportSize({width:390,height:650});await open(page,'panels/portfolio/');
 await page.waitForSelector('.efhc-panel-tile');
 const read=()=>page.evaluate(()=>{
  const list=document.querySelector('.efhc-panels-card-surface'),card=list.querySelector('.efhc-panel-tile');
  return {list:list.getBoundingClientRect().height,card:card.getBoundingClientRect().toJSON(),maxHeight:getComputedStyle(list).maxHeight,count:list.querySelectorAll('.efhc-panel-tile').length};
 });
 const small=await read();
 await page.setViewportSize({width:390,height:1000});await page.waitForTimeout(200);
 const tall=await read();
 assert.ok(tall.list-small.list>300,`list did not receive additional height: ${JSON.stringify({small,tall})}`);
 assert.ok(Math.abs(tall.card.height-small.card.height)<1 && Math.abs(tall.card.width-small.card.width)<1,'panel cards were resized');
 assert.equal(tall.maxHeight,'none');assert.equal(tall.count,small.count,'resize loaded another batch');
 const last=await page.evaluate(()=>{
  const main=document.querySelector('#efhc-main-content'),list=document.querySelector('.efhc-panels-card-surface');
  main.scrollTop=main.scrollHeight;
  return {bottom:document.querySelector('.efhc-panels-list-card').getBoundingClientRect().bottom,nav:document.querySelector('.efhc-game-nav').getBoundingClientRect().top,listOverflow:getComputedStyle(list).overflowY};
 });
 assert.ok(last.bottom<=last.nav+1 && last.nav-last.bottom<=12,JSON.stringify(last));
 assert.equal(last.listOverflow,'auto');
 if(artifacts){await fs.writeFile(`${artifacts}/user-height-results.json`,JSON.stringify({results,small,tall,last},null,2)+'\n');await page.screenshot({path:`${artifacts}/portfolio-adaptive-height.png`});}
 return results;
}
