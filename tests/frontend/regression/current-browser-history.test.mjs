import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../../../frontend/package.json',import.meta.url)),ts=require('typescript');
const file=new URL('../../../frontend/src/lib/appBackNavigation.ts',import.meta.url);
const js=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
function harness(current='/ranks',stack=['/','/panels','/referrals','/ranks']){
 const saved=new Map([['efhc_app_back_stack_v1',JSON.stringify(stack)]]),listeners={},replaced=[];
 let beforePop,modal=false;
 const router={asPath:current,pathname:current,events:{on(){},off(){}},beforePopState:fn=>{beforePop=fn;},replace:async path=>{replaced.push(path);return true;}};
 const window={location:{pathname:'/efhc'+current,search:'',hash:''},history:{state:{},length:2},sessionStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)},addEventListener:(n,f)=>{listeners[n]=f;},removeEventListener(){},requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout:()=>1};
 const document={body:{},documentElement:{dataset:{}},querySelectorAll:()=>modal?[{getClientRects:()=>[{}]}]:[],querySelector:()=>null,addEventListener(){},removeEventListener(){},dispatchEvent(){modal=false;return true;}};
 const exports={};const context={exports,window,document,navigator:{},Event,KeyboardEvent:class{},URL,Promise,require:name=>{
  if(name==='react')return {useEffect:fn=>fn(),useRef:value=>({current:value})};
  if(name==='./appBasePath')return {withoutAppBasePath:path=>path.replace(/^\/efhc(?=\/|\?|$)/,'')||'/'};
  if(name==='./telegram')return {getTelegramWebApp:()=>null,telegramBackButtonShow:()=>()=>{}};
  throw new Error(name);
 }};
 vm.runInNewContext(js,context);exports.useAppBackNavigation(router);
 return {router,window,replaced,modal:()=>{modal=true;},pop(path){window.location.pathname='/efhc'+path;let stopped=false;listeners.popstate({stopImmediatePropagation(){stopped=true;}});return stopped;},allow:()=>beforePop({})};
}
test('ordinary browser Back and Forward use their requested history destination',()=>{
 for(const [current,target] of [['/ranks','/referrals'],['/referrals','/ranks']]){
  const h=harness(current);assert.equal(h.pop(target),false,'native history traversal is not rewritten as logical Back');
  h.router.asPath=target; // The router may expose the destination before its callback.
  assert.equal(h.allow(),true);assert.deepEqual(h.replaced,[]);
  const nextFirst=harness(current);
  nextFirst.window.location.pathname='/efhc'+target;
  assert.equal(nextFirst.allow(),true);
  nextFirst.router.asPath=target;
  assert.equal(nextFirst.pop(target),false);
  assert.deepEqual(nextFirst.replaced,[],'fallback must not handle an already allowed Next traversal twice');
 }
});
test('same-URL direct-entry Back retains hierarchical Admin fallback',()=>{
 const h=harness('/admin/bank',['/admin/bank']);assert.equal(h.pop('/admin/bank'),true);assert.deepEqual(h.replaced,['/admin']);
});
test('browser Back closes a modal before changing its page',()=>{
 const h=harness();h.modal();assert.equal(h.pop('/ranks'),true);assert.deepEqual(h.replaced,[]);
});
test('native Android bridge keeps the logical route stack',()=>{
 const h=harness();h.window.__EFHC_ANDROID_BACK__();assert.deepEqual(h.replaced,['/referrals']);
});
