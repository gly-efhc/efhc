// Generate scoped shared-shell rules from immutable HTML v866 CSS.
// No new palettes, dimensions or design variants are invented here.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../frontend/',import.meta.url));
const require=createRequire(process.env.EFHC_FRONTEND_DEPENDENCIES || path.join(root,'package.json'));
const postcss=require('postcss');
const scope='.efhc-independent-shell[data-interface-app-mode="user"][data-efhc-source-styles="true"]';
const source=postcss.parse(fs.readFileSync(path.join(root,'public/FRONTEND_v866.css'),'utf8'));
function filter(container){
 const result=container.clone({nodes:[]});
 for(const node of container.nodes||[]){
  if(node.type==='rule'){
   const selectors=postcss.list.comma(node.selector).filter(s=>/\.efhc-(?:game-header|header-action|header-divider|game-nav)(?:[_\s.:[>]|$)/.test(s));
   if(selectors.length)result.append(node.clone({selector:selectors.map(s=>`${scope} :is(${s})`).join(',\n')}));
   // Shell-owned token definitions must override the superseded React palette
   // too. Copy only custom properties, leaving runtime viewport geometry alone.
   const roots=postcss.list.comma(node.selector).filter(s=>/\.efhc-independent-shell[^ >+~]*$/.test(s));
   const tokens=(node.nodes||[]).filter(n=>n.type==='decl'&&n.prop.startsWith('--'));
   if(roots.length&&tokens.length)result.append(node.clone({selector:roots.map(s=>`${scope}:is(${s})`).join(',\n'),nodes:tokens.map(n=>n.clone())}));
  }else if(node.type==='atrule'&&['media','supports','container'].includes(node.name)){
   const kept=filter(node);if(kept.nodes.length)result.append(kept);
  }
 }
 return result;
}
const adapter=`/* Generated from frozen FRONTEND_v866.css by site/ci/parity/generate_shell.mjs.
   Scope: USER header/navigation only. Admin and Shop do not match. */\n${filter(source).toString().replace(/[ \t]+$/gm, '').trimEnd()}\n`;
const destination=path.join(root,'public/user-shell.css');
if(process.argv.includes('--check')){
 if(fs.readFileSync(destination,'utf8')!==adapter)throw Error('v866 shared-shell adapter drift');
 console.log('V866_REACT_SHELL_DERIVATION=PASS');
}else fs.writeFileSync(destination,adapter);
await import('./generate_referrals.mjs');
