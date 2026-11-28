import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const reference=JSON.parse(await fs.readFile(new URL('./panels-activation-reference.json',import.meta.url)));

export async function verifyPanelsActivationReference(page,{open,artifacts}){
 await open(page,'panels/');await page.mouse.move(12,12);
 await page.locator('.efhc-interface-customization-button').click();
 const card=page.locator('.efhc-panels-activation-card[data-pa="PA-01"]');
 const results=[];
 for(let theme=1;theme<=10;theme++){
  await page.waitForFunction(i=>document.documentElement.dataset.colorThemeId==='CT-'+String(i).padStart(2,'0'),theme);
  for(const width of reference.captured_viewports){
   await page.setViewportSize({width,height:844});
   const actual=await card.evaluate(e=>{
    const grid=e.querySelector(':scope > .grid > .grid'),gs=getComputedStyle(grid);
    return{columns:gs.gridTemplateColumns.split(/\s+/).length,figures:[...grid.querySelectorAll('.tabular-nums')].map(n=>{const s=getComputedStyle(n);return{text:n.textContent,overflow:s.overflow,textOverflow:s.textOverflow,whiteSpace:s.whiteSpace,fontSize:parseFloat(s.fontSize),fontWeight:s.fontWeight,scroll:n.scrollWidth,client:n.clientWidth}}),cta:e.querySelector('.efhc-panels-activate').getBoundingClientRect().height};
   });
   const expected=width<=reference.breakpoint_max_px?reference.mobile:reference.desktop;
   assert.equal(actual.columns,expected.columns,`v866 PA-01 columns at ${width}`);
   assert.equal(actual.figures.length,2);assert.equal(actual.figures[0].text,'100 EFHC');
   assert.match(actual.figures[1].text,/\d+\.\d{8} EFHC/,'underlying D8 value unchanged');
   for(const figure of actual.figures){
    assert.equal(figure.overflow,expected.overflow);assert.equal(figure.textOverflow,expected.textOverflow);
    assert.equal(figure.whiteSpace,reference.number_white_space);assert.equal(figure.fontWeight,reference.number_font_weight);
    assert.ok(Math.abs(figure.fontSize-reference.number_font_px)<.02,'do not shrink the number to mask a bad grid');
    if(expected.columns===1)assert.ok(figure.scroll<=figure.client+1,'mobile D8 value must fit fully');
   }
   assert.ok(Math.abs(actual.cta-reference.cta_height_px)<.1,'activation button geometry unchanged');
   results.push({theme,width,...actual});
   if(artifacts&&theme===1&&[320,390,1440].includes(width))await card.screenshot({path:`${artifacts}/pa01-restored-${width}.png`});
  }
  if(theme<10)await page.locator('[data-color-theme-control="true"]').click();
 }
 if(artifacts)await fs.writeFile(`${artifacts}/pa01-reference-results.json`,JSON.stringify({source:reference.source_html_sha256,results},null,2)+'\n');
}
