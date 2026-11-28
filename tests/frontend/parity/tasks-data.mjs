/** Hydrated Tasks UI must survive valid zeroes and malformed 200 responses. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(process.env.EFHC_BROWSER_TOOLS||new URL('../../../frontend/package.json',import.meta.url))('playwright-core');
export async function verifyTasksData({base,artifacts}={}){
 const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
 const results=[];
 try{for(const width of [390,1440])for(const initial of ['scientific','valid']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let mode=initial;
  await context.route('**/*',async r=>{
   if(new URL(r.request().url()).origin===new URL(base).origin)return r.continue();
   const headers={'Access-Control-Allow-Origin':new URL(base).origin,'Access-Control-Allow-Credentials':'true','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':r.request().headers()['access-control-request-headers']||'Authorization,Content-Type'};
   if(r.request().method()==='OPTIONS')return r.fulfill({status:204,headers});
   if(new URL(r.request().url()).pathname==='/api/tasks/catalog'){
    return r.fulfill({status:200,headers,contentType:'application/json',body:JSON.stringify({items:[{id:'1',code:'C0036_TASK_READ_TEST',title:'Task',bonus_efhc:mode==='valid'?'0.00000000':'0E-8',is_active:true,kind:null,meta:null}]})});
   }
   return r.fulfill({status:401,headers,contentType:'application/json',body:'{}'});
  });
  try{
   const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/tasks/catalog');
   await page.goto(base+'tasks/',{waitUntil:'domcontentloaded'});await response;await page.waitForTimeout(1200);
   assert.equal(await page.locator('[data-public-surface="tasks"] .efhc-tasks-grid').count(),1,'loaded payload must not replace the Tasks page');
   assert.equal(await page.locator('[data-app-render-error]').count(),0,'caught React errors cannot count as a visible page');
   if(initial==='valid'){
    assert.equal(await page.locator('[data-task-card]').count(),1);assert.equal(await page.locator('.efhc-task-reward-value').innerText(),'0.00000000');
    results.push({width,case:'valid-zero',status:'PASS'});
    mode='scientific';const updated=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/tasks/catalog');
    await page.dispatchEvent('body','pointerdown');await updated;await page.waitForTimeout(1200);
    assert.equal(await page.locator('[data-public-surface="tasks"] .efhc-tasks-grid').count(),1);
    assert.equal(await page.locator('[data-task-card]').count(),1,'malformed refresh retains cached valid card');
    assert.equal(await page.locator('.efhc-task-reward-value').innerText(),'0.00000000');
    assert.equal(await page.locator('[data-app-render-error]').count(),0);
    results.push({width,case:'malformed-refresh-keeps-cache',status:'PASS'});
   }else results.push({width,case:'malformed-first-load-keeps-page',status:'PASS'});
  }finally{await context.unrouteAll({behavior:'ignoreErrors'});await context.close();}
 }}finally{await browser.close();if(artifacts){await fs.mkdir(artifacts,{recursive:true});await fs.writeFile(artifacts+'/tasks-data.json',JSON.stringify({results},null,2));}}
 return results;
}
