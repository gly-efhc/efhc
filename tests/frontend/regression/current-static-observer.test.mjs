import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../parity/static-pages.mjs',import.meta.url),'utf8');
const observer=source.slice(source.indexOf('function observe(){'),source.indexOf('async function assertSurface'));
function harness(path='/efhc/admin/panels/'){
 let read,main=true,control=false;
 const context={window:{},location:{pathname:path},document:{querySelector(selector){
  if(selector==='#efhc-main-content')return main?{}:null;
  if(selector==='[data-admin-user-profile="profile-composition"]')return {querySelector:()=>control?{}:null};
  if(selector==='[data-admin-primitive="page"]')return {};
  if(selector==='[data-app-navigation="exit-admin"]')return control?{}:null;
  return null;
 }},MutationObserver:class{constructor(callback){read=callback;}observe(){}}};
 vm.runInNewContext(observer+'observe();',context);
 return {read:()=>read(),setMain:value=>{main=value;},setControl:value=>{control=value;},state:context.window.__efhcStaticObservation};
}
test('streamed Admin HTML wrapper before its controls is not a page removal',()=>{
 const h=harness();h.read();assert.equal(h.state.adminReplaced,false);
 h.setControl(true);h.read();assert.equal(h.state.adminSeen,true);assert.equal(h.state.adminReplaced,false);
});
test('Admin controls removed after mounting are detected on normal and Users routes',()=>{
 for(const route of ['/efhc/admin/bank/','/efhc/admin/users/']){
  const h=harness(route);h.setControl(true);h.read();h.setControl(false);h.read();assert.equal(h.state.adminReplaced,true);
 }
});
test('loss of an already mounted USER page is still detected',()=>{
 const h=harness('/efhc/');h.read();h.setMain(false);h.read();assert.equal(h.state.lost,true);
});
