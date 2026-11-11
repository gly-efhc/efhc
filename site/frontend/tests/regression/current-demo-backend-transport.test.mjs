/** Cycle0032: behavioral network-contract checks, no deleted browser DEMO engine. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const ts=require('typescript');
const root=fileURLToPath(new URL('../../src/',import.meta.url));
function harness({origin='https://demo-api.example.org',auth='Bearer TEST_OPERATOR',onRequest,moduleMocks={}}={}){
 const calls=[];
 let cleared=0;
 let issued=null;
 const cache=new Map();
 const fakeApi={
  ApiError:class ApiError extends Error{constructor(args){super('EFHC_API_REQUEST_FAILED');Object.assign(this,args);}},
  normalizeApiPath:p=>p.startsWith('/api/')?p:'/api'+p,
 };
 const env={NEXT_PUBLIC_EFHC_DEMO_API_ORIGIN:origin,NEXT_PUBLIC_EFHC_DATA_SOURCE:'demo_backend'};
 const mocks={
  'lib/api':fakeApi,
  'lib/auth-session':{
   getAuthAuthorizationHeader:()=>issued ? 'Bearer '+issued.access_token : auth,
   storeAuthSession:credential=>{issued=credential;},
   clearAuthSession:()=>{cleared++;issued=null;},
  },
 };
 Object.assign(mocks,moduleMocks);
 const context=vm.createContext({process:{env},URL,URLSearchParams,AbortController,AbortSignal,Response,Headers,Blob,console,Promise,Date,Error,JSON,setTimeout,clearTimeout,fetch:async(url,opts={})=>{
  calls.push({url:String(url),options:opts});
  if(onRequest)return onRequest(String(url),opts);
  if(String(url).endsWith('/api/staging/session'))return Response.json({ok:true,global_id:issued?.access_token?.startsWith('S')?'0000003001':'0000000002',csrf:issued?.access_token?.startsWith('S')?'next-csrf':'csrf-token',mode:'operator'});
  if(String(url).endsWith('/api/staging/guest'))return Response.json({ok:true,global_id:'0000003001',csrf:'test-guest-csrf',mode:'genesis-test-guest',scope:'guest',guest_resume_token:'R'.repeat(48),demo_bearer_token:'P'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600});
  if(String(url).endsWith('/api/staging/login'))return Response.json({ok:true,global_id:'0000000002',csrf:'login-csrf',mode:'operator',demo_bearer_token:'L'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600});
  if(String(url).endsWith('/api/staging/select-global-id'))return Response.json({ok:true,global_id:'0000003001',csrf:'next-csrf',mode:'operator',demo_bearer_token:'S'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600});
  if(String(url).endsWith('/api/staging/logout'))return Response.json({ok:true});
  if(String(url).endsWith('/api/sync/me'))return Response.json({profile:{global_id:'0000000002'}});
  return Response.json({code:'not-found'},{status:404});
 }});
 function load(rel){
  rel=rel.replace(/\\/g,'/');
  const key=rel.replace(/\.(tsx?|json)$/,'');
  if(mocks[key])return mocks[key];
  let f=path.join(root,rel);
  if(!fs.existsSync(f)){if(fs.existsSync(f+'.ts'))f+='.ts';else if(fs.existsSync(f+'.tsx'))f+='.tsx';}
  if(cache.has(f))return cache.get(f).exports;
  const mod={exports:{}};cache.set(f,mod);
  const src=fs.readFileSync(f,'utf8');
  const output=ts.transpileModule(src,{fileName:f,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
  const customRequire=name=>name.startsWith('.')?load(path.relative(root,path.resolve(path.dirname(f),name))):require(name);
  vm.runInContext(`(function(require,module,exports){${output}\n})`,context,{filename:f})(customRequire,mod,mod.exports);
  return mod.exports;
 }
 return {load,env,calls,get cleared(){return cleared;}};
}
test('Backend API origin prefers canonical HTTPS address and accepts legacy variable during migration',()=>{
 const h=harness(),config=h.load('demo/config.ts');
 assert.equal(config.demoApiOrigin(),'https://demo-api.example.org','legacy configuration remains compatible');
 h.env.NEXT_PUBLIC_EFHC_BACKEND_API_ORIGIN='https://backend.example.org';
 assert.equal(config.demoApiOrigin(),'https://backend.example.org','canonical backend address overrides legacy Render origin');
 h.env.NEXT_PUBLIC_EFHC_BACKEND_API_ORIGIN='';
 assert.equal(config.demoApiOrigin(),'https://demo-api.example.org','legacy fallback is used only when canonical is empty');
});
test('Backend API origin rejects insecure, credentialed and malformed destinations',()=>{
 const h=harness(),config=h.load('demo/config.ts');
 for(const url of ['','http://demo-api.example.org','https://user:secret@demo-api.example.org','https://demo-api.example.org/db','https://demo-api.example.org/?token=1','https://demo-api.example.org/#secret']){
  h.env.NEXT_PUBLIC_EFHC_DEMO_API_ORIGIN='';
  h.env.NEXT_PUBLIC_EFHC_BACKEND_API_ORIGIN=url;
  assert.throws(()=>config.demoApiOrigin(),/EFHC_BACKEND_API_ORIGIN/);
 }
 h.env.NEXT_PUBLIC_EFHC_BACKEND_API_ORIGIN='http://invalid.example.org';
 h.env.NEXT_PUBLIC_EFHC_DEMO_API_ORIGIN='https://legacy-valid.example.org';
 assert.throws(()=>config.demoApiOrigin(),/EFHC_BACKEND_API_ORIGIN/,'invalid canonical endpoint must fail closed');
});
test('DEMO business request uses authenticated remote API, Idempotency-Key and server CSRF',async()=>{
 const h=harness(),bridge=h.load('demo/transport.ts');
 const result=await bridge.demoBackendTransport.request('/sync/me','POST',{body:{fresh:true},idempotencyKey:'unique-31',requestId:'trace-42',headers:{'X-EFHC-Handoff':'real-handoff'}});
 assert.equal(result.profile.global_id,'0000000002');
 assert.equal(h.calls.length,2,'CSRF session lookup then real backend request');
 const {url,options}=h.calls[1];
 assert.equal(url,'https://demo-api.example.org/api/sync/me');
 assert.equal(options.credentials,'include');
 assert.equal(options.cache,'no-store');
 assert.equal(options.headers['X-EFHC-Test-CSRF'],'csrf-token');
 assert.equal(options.headers['Idempotency-Key'],'unique-31');
 assert.equal(options.headers['X-Request-ID'],'trace-42');
 assert.equal(options.headers['X-EFHC-Handoff'],'real-handoff');
 assert.equal(options.headers.Authorization,'Bearer TEST_OPERATOR');
 assert.deepEqual(JSON.parse(options.body),{fresh:true});
});
test('unauthorized API response revokes DEMO session and returns an explicit error, not fixtures',async()=>{
 let hits=0;
 const h=harness({onRequest:()=>{hits++;return Response.json({detail:'expired'},{status:401});}});
 const demo=h.load('demo/transport.ts');
 await assert.rejects(()=>demo.demoBackendTransport.request('/wallets/me','GET',{}),error=>error.status===401);
 assert.equal(h.cleared,1);
 assert.equal(hits,1);
});
test('DEMO operator login and Global ID switching preserve server-issued bearer when cross-site cookies are blocked',async()=>{
 const h=harness({auth:null}),s=h.load('demo/session.ts');
 const login=await s.loginDemo('test-password');
 assert.equal(login.global_id,'0000000002');
 assert.equal(login.demo_bearer_token,undefined,'bearer must not leak into UI return value');
 const session=await s.sessionInfo();
 assert.equal(session.global_id,'0000000002');
 assert.equal(h.calls[1].options.headers.Authorization,'Bearer '+'L'.repeat(64));
 const selected=await s.selectDemoGlobalId('0000003001');
 assert.equal(selected.global_id,'0000003001');
 assert.equal(selected.demo_bearer_token,undefined);
 assert.equal(h.calls[2].options.headers['X-EFHC-Test-CSRF'],'csrf-token');
 assert.equal(h.calls[2].options.headers.Authorization,'Bearer '+'L'.repeat(64));
 assert.equal(h.calls[2].options.credentials,'include');
 assert.deepEqual(JSON.parse(h.calls[2].options.body),{global_id:'0000003001'});
 const renewed=await s.sessionInfo();
 assert.equal(renewed.ok,true);
 assert.equal(h.calls[3].options.headers.Authorization,'Bearer '+'S'.repeat(64));
 await assert.rejects(()=>s.selectDemoGlobalId('88'),/INVALID_GLOBAL_ID/);
 await s.logoutDemo();
 assert.equal(h.calls[4].options.headers['X-EFHC-Test-CSRF'],'next-csrf');
 assert.equal(h.calls[4].options.headers.Authorization,'Bearer '+'S'.repeat(64));
 assert.equal(h.cleared,1);
});
test('DEMO operator credential must be server-issued and not invented client-side',async()=>{
 const h=harness({auth:null,onRequest:()=>Response.json({ok:true,global_id:'0000000002',csrf:'unsafe',mode:'neon-test'})});
 await assert.rejects(()=>h.load('demo/session.ts').loginDemo('test-password'),/DEMO_SESSION_CREDENTIAL_MISSING/);
 assert.equal(h.calls.length,1);
});
test('registered transport preserves request options and raw binary response path',async()=>{
 const h=harness(),dispatcher=h.load('data/transport.ts');
 const seen=[];
 dispatcher.registerTransport({
  request:async(...args)=>{seen.push(args);return{value:'server'};},
  requestRaw:async(...args)=>{seen.push(args);return new Response('csv',{headers:{'Content-Type':'text/csv'}});},
 });
 const options={signal:new AbortController().signal,idempotencyKey:'test-replay'};
 assert.equal((await dispatcher.transportRequest('/sync/me','POST',options)).value,'server');
 assert.equal(await (await dispatcher.transportRawRequest('/admin/logs/export.csv','GET',{})).text(),'csv');
 assert.equal(seen[0][2],options);
 assert.equal(seen[1][0],'/admin/logs/export.csv');
});

test('public TEST guest is never an Admin; server 403 remains authoritative',async()=>{
 const h=harness({auth:null,onRequest:async(url)=>{
  if(url.endsWith('/api/staging/guest'))return Response.json({
   ok:true,global_id:'0000003001',csrf:'guest-csrf',mode:'genesis-test-guest',
   scope:'guest',guest_resume_token:'R'.repeat(48),
   demo_bearer_token:'P'.repeat(64),
   expires_at_epoch:Math.floor(Date.now()/1000)+3600
  });
  if(url.endsWith('/api/admin/access'))return Response.json(
   {detail:'TEST_ADMIN_GLOBAL_ID_NOT_ALLOWED'},{status:403}
  );
  return Response.json({});
 }});
 const session=h.load('demo/session.ts');
 const ctx=await session.loginDemoGuest();
 assert.equal(ctx.global_id,'0000003001');
 assert.equal(ctx.demo_bearer_token,undefined,'secret must not leak to profile');
 assert.equal(h.calls[0].url,'https://demo-api.example.org/api/staging/guest');
 await assert.rejects(
  h.load('demo/transport.ts').demoRawRequest('/admin/access','GET'),
  error=>error.status===403
 );
 assert.equal(h.calls[1].url,'https://demo-api.example.org/api/admin/access');
 assert.equal(h.calls[1].options.headers.Authorization,'Bearer '+'P'.repeat(64));
});

test('late 401 from an older request must not revoke a newly issued TEST session',async()=>{
 let finish;
 const pendingResponse=new Promise(resolve=>{finish=resolve;});
 const h=harness({onRequest:async(url)=>{
  if(url.endsWith('/api/staging/guest'))return Response.json({ok:true,global_id:'0000003001',csrf:'fresh-csrf',mode:'genesis-test-guest',scope:'guest',guest_resume_token:'R'.repeat(48),demo_bearer_token:'N'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600});
  return pendingResponse;
 }});
 const transport=h.load('demo/transport.ts');
 const rejected=assert.rejects(transport.demoBackendTransport.request('/wallets/me','GET',{}),e=>e.status===401);
 await h.load('demo/session.ts').loginDemoGuest();
 finish(Response.json({detail:'old request expired'},{status:401}));await rejected;
 assert.equal(h.cleared,0,'an old response must not destroy the newer session');
});

test('a failed operator password must preserve the existing TEST guest session',async()=>{
 const h=harness({onRequest:async()=>Response.json({detail:'DEMO_BAD_CREDENTIALS'},{status:401})});
 await assert.rejects(h.load('demo/session.ts').loginDemo('wrong'),/HTTP_401/);
 assert.equal(h.cleared,0,'invalid replacement credentials do not revoke the current session');
});

test('401 for an explicit Authorization override never revokes another current credential',async()=>{
 const h=harness({onRequest:async()=>Response.json({detail:'expired other token'},{status:401})});
 await assert.rejects(h.load('demo/transport.ts').demoBackendTransport.request('/wallets/me','GET',{headers:{Authorization:'Bearer OTHER_SESSION'}}),e=>e.status===401);
 assert.equal(h.cleared,0);
});

test('failed CSRF synchronization does not send a protected operation with an empty proof',async()=>{
 const h=harness({onRequest:async()=>Response.json({detail:'unavailable'},{status:503})});
 await assert.rejects(h.load('demo/transport.ts').demoBackendTransport.request('/panels/activate','POST',{}));
 assert.equal(h.calls.length,1,'stop at failed CSRF session read, do not submit the operation');
});

test('late public guest issuance cannot replace a newer operator session', async()=>{
 let finishGuest;
 const h=harness({auth:null,onRequest:async(url)=>{
  if(url.endsWith('/guest'))return await new Promise(resolve=>{finishGuest=resolve;});
  if(url.endsWith('/login'))return Response.json({ok:true,global_id:'0000000002',csrf:'operator-csrf',mode:'operator',scope:'operator',demo_bearer_token:'L'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600});
  if(url.endsWith('/session'))return Response.json({ok:true,global_id:'0000000002',csrf:'operator-csrf',mode:'operator'});
  return Response.json({});
 }});
 const s=h.load('demo/session.ts'), old=s.loginDemoGuest();
 await s.loginDemo('test-password');
 finishGuest(Response.json({ok:true,global_id:'0000003001',csrf:'old-csrf',mode:'genesis-test-guest',scope:'guest',guest_resume_token:'R'.repeat(48),demo_bearer_token:'P'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600}));
 await assert.rejects(()=>old,/DEMO_SESSION_REPLACED/);
 await s.sessionInfo();
 assert.equal(h.calls.at(-1).options.headers.Authorization,'Bearer '+'L'.repeat(64));
 assert.equal(await s.sessionCsrf(),'operator-csrf');
 assert.equal(h.cleared,0);
});

test('late session metadata cannot apply CSRF proof from a superseded credential', async()=>{
 let finishSession;
 const h=harness({onRequest:async(url)=>{
  if(url.endsWith('/session'))return await new Promise(resolve=>{finishSession=resolve;});
  return Response.json({ok:true,global_id:'0000000002',csrf:'new-csrf',mode:'operator',demo_bearer_token:'L'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600});
 }});
 const s=h.load('demo/session.ts'), old=s.sessionInfo();
 await s.loginDemo('test-password');
 finishSession(Response.json({ok:true,global_id:'0000003001',csrf:'old-csrf',mode:'genesis-test-guest'}));
 await assert.rejects(()=>old,/DEMO_SESSION_REPLACED/);
 assert.equal(await s.sessionCsrf(),'new-csrf');
});

test('obsolete auth proof cannot replace the display owner of a newer session', async()=>{
 let resolveProof, authorization='Bearer OLD_PROOF'; const owners=[];
 const h=harness({moduleMocks:{
  'lib/auth-session':{getAuthAuthorizationHeader:()=>authorization, validateAuthSessionContext:value=>value},
  'services/authSession.service':{requestAuthSessionContext:()=>new Promise(resolve=>{resolveProof=resolve;})},
  'lib/displayOwner':{recordResolvedDisplayOwner:owner=>owners.push(owner)},
 }});
 const client=h.load('lib/auth-session-client.ts'), old=client.fetchAuthSessionContext();
 authorization='Bearer NEW_PROOF';
 resolveProof({global_id:'0000003001',provider:'guest',roles:['admin']});
 await assert.rejects(()=>old,/AUTH_SESSION_REPLACED/);
 assert.deepEqual(owners,[],'stale response must never bind or restore another owner cache');
 const current=client.fetchAuthSessionContext();
 resolveProof({global_id:'0000000002',provider:'operator',roles:['admin']});
 assert.equal((await current).global_id,'0000000002');
 assert.deepEqual(owners,['0000000002']);
});

test('anonymous 401 must not cancel an in-flight public guest issuance',async()=>{
 let finishGuest;
 const h=harness({auth:null,onRequest:async url=>{
  if(url.endsWith('/guest'))return new Promise(resolve=>{finishGuest=resolve;});
  return Response.json({detail:'DEMO_SESSION_REQUIRED'},{status:401});
 }});
 const s=h.load('demo/session.ts'),guest=s.loginDemoGuest();
 await assert.rejects(()=>h.load('demo/transport.ts').demoBackendTransport.request('/tasks/catalog','GET',{}));
 finishGuest(Response.json({ok:true,global_id:'0000003001',csrf:'guest-csrf',mode:'genesis-test-guest',scope:'guest',guest_resume_token:'R'.repeat(48),demo_bearer_token:'P'.repeat(64),expires_at_epoch:Math.floor(Date.now()/1000)+3600}));
 assert.equal((await guest).global_id,'0000003001');assert.equal(h.cleared,0);
});
