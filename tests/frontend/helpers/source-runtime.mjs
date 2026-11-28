import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
const require=createRequire(process.env.EFHC_FRONTEND_DEPENDENCIES || new URL('../../../frontend/package.json',import.meta.url)),ts=require('typescript');
const root=fileURLToPath(new URL('src/', process.env.EFHC_FRONTEND_TEST_ROOT ? pathToFileURL(process.env.EFHC_FRONTEND_TEST_ROOT.replace(/\/$/, '') + '/') : new URL('../../../frontend/',import.meta.url)));
export function sourceRuntime({storage=new Map(),session=new Map(),overrides={}}={}){
 const modules=new Map();
 const sessionStorage={getItem:k=>session.get(k)??null,setItem:(k,v)=>session.set(k,String(v)),removeItem:k=>session.delete(k)};
 const window={localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)},sessionStorage,matchMedia:()=>({matches:true}),setTimeout,clearTimeout};
 const context=vm.createContext({window,sessionStorage,console,process:{env:{}},URL,URLSearchParams,AbortController,Blob,Event,performance,setTimeout,clearTimeout,structuredClone,Date});
 function load(filename){
  filename=path.resolve(filename);
  if(!fs.existsSync(filename)||!fs.statSync(filename).isFile())filename=['.ts','.tsx'].map(ext=>filename+ext).find(p=>fs.existsSync(p))||filename+'.ts';
  if(modules.has(filename))return modules.get(filename).exports;
  const module={exports:{}};modules.set(filename,module);
  if(filename.endsWith('.json')){module.exports=JSON.parse(fs.readFileSync(filename,'utf8'));return module.exports;}
  const code=ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React,esModuleInterop:true,resolveJsonModule:true}}).outputText;
  vm.runInContext(`(function(require,module,exports){${code}\n})`,context,{filename})(name=>{
   if(name in overrides)return overrides[name];
   return name.startsWith('.')?load(path.resolve(path.dirname(filename),name)):require(name);
  },module,module.exports);
  return module.exports;
 }
 return {load:relative=>load(path.join(root,relative)),storage,session,window};
}
