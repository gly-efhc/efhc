import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

// Compare the painted prefix against a full-progress raster. The same CSS
// declaration can pass a style comparison while its segments collapse at 5%.
export async function verifyProgress20Grid(page,track,{group,width,artifacts}={}) {
 assert.equal(await track.getAttribute('data-pb'),'PB-09');
 const scope=group==='PB'?'.efhc-energy-page':'.efhc-referrals-shell';
 const selector=`${scope} .efhc-energy-progress-track[data-pb="PB-09"] > .efhc-energy-progress-fill`;
 const style=await page.addStyleTag({content:`${selector}{width:100%!important;transition:none!important;animation:none!important}`});
 let phase='normal';
 const capture=async percent=>{
  await style.evaluate((el,{selector,percent})=>{el.textContent=`${selector}{width:${percent}%!important;transition:none!important;animation:none!important}`},{selector,percent});
  const geometry=await track.evaluate(el=>{const t=el.getBoundingClientRect(),f=el.firstElementChild.getBoundingClientRect();return {rail:t.width,fill:f.width,left:f.left-t.left,height:t.height,backgroundSize:getComputedStyle(el.firstElementChild).backgroundSize}});
  const png=await track.screenshot();
  const pixels=await page.evaluate(async data=>{const img=new Image();img.src=data;await img.decode();const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);const row=ctx.getImageData(0,Math.floor(canvas.height/2),canvas.width,1).data;return Array.from({length:canvas.width},(_,i)=>[...row.slice(i*4,i*4+3)])},'data:image/png;base64,'+png.toString('base64'));
  if(artifacts){await fs.mkdir(artifacts,{recursive:true});await fs.writeFile(`${artifacts}/progress20-${group}-${width}-${phase}-${percent}.png`,png)}
  return {percent,geometry,pixels};
 };
 const results=[];
 try{
  const empty=await capture(0),full=await capture(100);
  assert.ok(empty.geometry.fill<.1,'zero progress must stay empty');
  const ink=(sample,x)=>sample.pixels[x].reduce((n,c,k)=>n+Math.abs(c-empty.pixels[x][k]),0)>120;
  const gaps=[];let start=null;
  for(let x=3;x<full.pixels.length-3;x++){
   if(!ink(full,x)&&start===null)start=x;
   if(ink(full,x)&&start!==null){gaps.push({x:start,width:x-start});start=null}
  }
  assert.equal(gaps.length,9,'full track must retain the ten authored segments');
  assert.ok(gaps.every(g=>g.width>=2&&g.width<=4),'authored 3px gaps changed');
  for(const percent of [1,5,7.78,10,25,50,74,100]){
   const sample=await capture(percent);
   const visibleEnd=Math.min(sample.pixels.length-3,Math.floor(sample.geometry.left+sample.geometry.fill)-3);
   let compared=0,mismatches=0;const displaced=[];
   for(let x=3;x<visibleEnd;x++){
    compared++;
    if(ink(sample,x)!==ink(full,x)){mismatches++;if(ink(sample,x)!==ink(full,x-1)&&ink(sample,x)!==ink(full,x+1))displaced.push(x)}
   }
   // Fractional rail pixels may shift antialiasing one pixel at a gap edge.
   // Interior displacement is forbidden, regardless of how few pixels differ.
   assert.deepEqual(displaced,[],`${group} at ${percent}% compressed or shifted segments: ${displaced.join(',')}`);
   assert.ok(sample.pixels.some((_,x)=>ink(sample,x)),`${group} at ${percent}% has no visible segment`);
   results.push({percent,geometry:sample.geometry,compared,mismatches,displaced});
  }
  // Container-relative paint must follow a resized rail without changing progress.
  await style.evaluate((el,selector)=>{el.textContent=`${selector}{width:25%!important;transition:none!important}`},selector);
  const before=await track.evaluate(el=>({width:el.clientWidth,paint:parseFloat(getComputedStyle(el.firstElementChild).backgroundSize)}));
  const oldWidth=await track.evaluate(el=>el.style.width);
  try{
   phase='resized';
   await track.evaluate(el=>el.style.setProperty('width','220px','important'));
   const resized=await capture(25),smallEmpty=await capture(0),smallFull=await capture(100);
   assert.ok(Math.abs(parseFloat(resized.geometry.backgroundSize)-(smallFull.geometry.fill))<=1,'paint canvas does not follow the resized rail');
   let compared=0,mismatches=0;const displaced=[];
   for(let x=3;x<Math.floor(resized.geometry.left+resized.geometry.fill)-3;x++){
    const color=(s)=>s.pixels[x].reduce((n,c,k)=>n+Math.abs(c-smallEmpty.pixels[x][k]),0)>120;
    compared++;if(color(resized)!==color(smallFull)){mismatches++;const adjacent=[x-1,x+1].map(i=>smallFull.pixels[i].reduce((n,c,k)=>n+Math.abs(c-smallEmpty.pixels[i][k]),0)>120);if(!adjacent.includes(color(resized)))displaced.push(x)}
   }
   assert.deepEqual(displaced,[],'resized rail compresses the segments');
   results.push({resize:true,before,after:resized.geometry,compared,mismatches,displaced});
  }finally{await track.evaluate((el,value)=>{el.style.removeProperty('width');if(value)el.style.width=value},oldWidth)}
  if(artifacts)await fs.writeFile(`${artifacts}/progress20-${group}-${width}.json`,JSON.stringify({group,width,gaps,results},null,2));
  return {group,width,gaps,results};
 }finally{await style.evaluate(el=>el.remove())}
}
