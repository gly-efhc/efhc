// Project only the immutable Referrals/base-card selectors onto the React DOM.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../frontend/',import.meta.url));
const require=createRequire(process.env.EFHC_FRONTEND_DEPENDENCIES||path.join(root,'package.json'));
const postcss=require('postcss'),source=postcss.parse(fs.readFileSync(path.join(root,'public/FRONTEND_v866.css'),'utf8'));
const user='.efhc-independent-shell[data-interface-app-mode="user"]';
const page='.efhc-referrals-shell[data-referrals-reference="true"]';
// Preserve source ID specificity without adding a live ID that would alter RP.
const sourcePage=`:is(#referralsPage,${page})`;
const map={
 '.source-game-hero':'.efhc-game-hero','.source-hero-head':'.efhc-game-hero_head',
 '.source-hero-kicker':'.efhc-game-kicker','.source-hero-title':'.efhc-game-title','.source-hero-detail':'.efhc-game-detail',
 '.source-stats':'.efhc-game-stats','.source-stat-label':'.efhc-game-stat_label','.source-stat-value':'.efhc-game-stat_value','.source-stat':'.efhc-game-stat',
 '.source-card-title':':is(.efhc-card > .text-lg.font-semibold,.efhc-referral-card-title)',
 '.source-card':'.efhc-card','.source-ref-row':'.efhc-list-row','.source-segmented':'.efhc-segmented',
 '.source-row':'.efhc-referral-level-heading','.source-muted':'.efhc-text-muted2','.source-value':'[data-referral-link-value]',
 '.source-button.secondary':'.efhc-btn-secondary:not([data-referral-share-kind])',
 '.source-button':':is(.efhc-btn-primary,.efhc-btn-secondary,.efhc-btn-ghost):not([data-referral-share-kind])',
 '.source-pill':'.efhc-referral-level-pill',
 '.standalone-bonus-earnings-strip':'.efhc-bonus-earnings-strip',
};
function project(selector){
 const own=/#referralsPage|\.efhc-referrals-shell/.test(selector);
 const generic=/\.(?:source-(?:game-hero|hero-(?:head|kicker|title|detail)|stats|stat(?:-label|-value)?|card(?:-title)?|row|muted|value|button|pill)|standalone-(?:referral-achievement|bonus-earnings-strip)|efhc-referral-achievement-[a-z-]+)\b/.test(selector);
 if(!own&&!generic)return null;
 if(/efhc-energy-progress|data-referrals-progress-bar/.test(selector))return null;
 let result=selector.replace(/\.efhc-referrals-shell/g,page).replace(/#referralsPage/g,sourcePage);
 for(const [from,to] of Object.entries(map).sort((a,b)=>b[0].length-a[0].length))result=result.split(from).join(to);
 result=result.replace(/\.standalone-referral-achievement-/g,'.efhc-referral-achievement-').replace(/\[data-state=/g,'[data-referral-level-state=').replace(/(\.efhc-referral-achievement-nodes\s*>\s*div\s*>\s*)b\b/g,'$1.efhc-referral-achievement-dot');
 if(result.includes('.efhc-referral-achievement-nodes'))result=result.replace(/(^|[\s>+~])b(?=$|[\s.:[>+~])/g,'$1.efhc-referral-achievement-dot');
 // Mixed :is() lists in the source include other routes. Constrain the final
 // target itself to this page, including the root and pseudo-elements.
 const pseudo=result.match(/(::[a-z-]+(?:\([^)]*\))?)$/)?.[1]||'';
 if(pseudo)result=result.slice(0,-pseudo.length);
 const target=own?`${user} :is(${result})`:`${user} :where(${page}) :is(${result})`;
 return `${target}:where(${page},${page} *)${pseudo}`;
}
function extract(container){
 const result=container.clone({nodes:[]});
 for(const node of container.nodes||[]){
  if(node.type==='rule'){
   const selectors=postcss.list.comma(node.selector).map(project).filter(Boolean);if(!selectors.length)continue;
   // Preserve authored values and priorities; do not recolor text/materials.
   result.append(node.clone({selector:selectors.join(',\n')}));
  }else if(node.type==='atrule'&&['media','supports','container'].includes(node.name)){const nested=extract(node);if(nested.nodes.length)result.append(nested);}
 }
 return result;
}
const css=`/* Generated from frozen FRONTEND_v866.css. Referrals only; original authored values and priorities preserved. */
${extract(source)}
${user} ${page} {display:grid!important;gap:.65rem!important;min-width:0!important;}
/* The authored hero owns its padding; React's extra wrappers add no second inset. */
${user} ${page} .efhc-game-hero_content {padding:0!important;}
${user} ${page} .efhc-game-hero_body {margin-top:0!important;}
${user} ${page} .efhc-game-hero_glow {display:none!important;}
${user} ${page} .efhc-referrals-link-card {margin-top:.55rem!important;padding:.62rem!important;background:rgba(5,10,18,.5)!important;}
${user} ${page} .efhc-referral-card-title {margin:0!important;}
`;
const dest=path.join(root,'public/referrals.css');
if(process.argv.includes('--check')){if(fs.readFileSync(dest,'utf8')!==css)throw Error('v866 referrals adapter drift');console.log('V866_REACT_REFERRALS_DERIVATION=PASS')}else fs.writeFileSync(dest,css);
