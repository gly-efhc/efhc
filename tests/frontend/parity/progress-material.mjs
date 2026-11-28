// Independent donor comparison: keep gradient stops, alpha, glass, shadows and
// pseudo-elements observable while allowing the OWNER-required active CT hue.
export function readProgressMaterial(track) {
 const alpha=token=>{
  const match=token.match(/\/\s*([\d.]+)\s*\)$/)||token.match(/^rgba\([^)]*,\s*([\d.]+)\s*\)$/);
  return match?Math.round(Math.round(Number(match[1])*255)/255*1e6)/1e6:1;
 };
 const paint=value=>value.replace(/\b(?:rgba?|color)\([^)]*\)/g,token=>`tone(${alpha(token)})`).replace(/\s+/g,'');
 const pseudo=(node,part)=>{const s=getComputedStyle(node,part);return s.content==='none'?{content:'none'}:{content:s.content,paint:paint(s.backgroundImage),alpha:alpha(s.backgroundColor),shadow:paint(s.boxShadow),blend:s.mixBlendMode,opacity:s.opacity,size:s.backgroundSize,clip:s.clipPath};};
 const fill=track.querySelector('.efhc-energy-progress-fill'),t=getComputedStyle(track),f=getComputedStyle(fill);
 return {
  track:{paint:paint(t.backgroundImage),alpha:alpha(t.backgroundColor),border:t.borderWidth,borderStyle:t.borderStyle,edgeAlpha:t.borderTopWidth==='0px'?null:alpha(t.borderTopColor),radius:t.borderRadius,padding:t.padding,shadow:paint(t.boxShadow),glass:t.backdropFilter,before:pseudo(track,'::before'),after:pseudo(track,'::after')},
  fill:{paint:paint(f.backgroundImage),alpha:alpha(f.backgroundColor),radius:f.borderRadius,shadow:paint(f.boxShadow),clip:f.clipPath,animation:f.animationName,size:f.backgroundSize,left:f.left,before:pseudo(fill,'::before'),after:pseudo(fill,'::after')},
 };
}

// Check actual computed foreground paints, not merely custom-property tokens.
// Neutral metal/glass highlights and transparent gaps are allowed.
export function readProgressAccent(track) {
 const fill=track.querySelector('.efhc-energy-progress-fill'),style=getComputedStyle(fill);
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 canvas.width=canvas.height=1;
 const rgb=paint=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=paint;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data]};
 const hue=([r,g,b])=>{const max=Math.max(r,g,b),min=Math.min(r,g,b),d=max-min;if(d<8)return null;return ((max===r?(g-b)/d:max===g?(b-r)/d+2:(r-g)/d+4)*60+360)%360};
 const expected=hue(rgb(getComputedStyle(track).getPropertyValue('--efhc-ct-accent').trim()));
 const tokens=[style.backgroundImage,style.backgroundColor,style.boxShadow].join(' ').match(/\b(?:rgba?|color)\([^)]*\)/g)||[];
 const differences=tokens.map(token=>rgb(token)).filter(color=>color[3]>3).map(hue).filter(h=>h!==null).map(h=>Math.min(Math.abs(h-expected),360-Math.abs(h-expected)));
 return {expected,differences};
}

// Exact route-to-route comparison includes palette values, not only structure.
export function readProgressAppearance(track) {
 const read=el=>{const s=getComputedStyle(el);return {height:s.height,background:s.backgroundImage,color:s.backgroundColor,border:s.borderWidth==='0px'?null:s.borderColor,borderWidth:s.borderWidth,radius:s.borderRadius,shadow:s.boxShadow,glass:s.backdropFilter,padding:s.padding,top:s.top,bottom:s.bottom,left:s.left,animation:s.animationName,size:s.backgroundSize,clip:s.clipPath}};
 const t=read(track);delete t.top;delete t.bottom;delete t.left;
 return {track:t,fill:read(track.firstElementChild)};
}

export function readProgressGeometry(track) {
 const fill=track.firstElementChild,t=track.getBoundingClientRect(),f=fill.getBoundingClientRect();
 const oldWidth=fill.style.getPropertyValue('width'),priority=fill.style.getPropertyPriority('width'),oldTransition=fill.style.transition,bounds=[];
 try{
  fill.style.transition='none';
  for(const width of ['0%','50%','100%']){
   fill.style.setProperty('width',width,'important');
   const r=fill.getBoundingClientRect();
   bounds.push({width,rendered:r.width,left:r.left-t.left,right:t.right-r.right,top:r.top-t.top,bottom:t.bottom-r.bottom,inside:r.left>=t.left-.1&&r.right<=t.right+.1&&r.top>=t.top-.1&&r.bottom<=t.bottom+.1});
  }
 }finally{fill.style.setProperty('width',oldWidth,priority);fill.style.transition=oldTransition}
 return {height:t.height,fillHeight:f.height,bounds};
}
