import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {sourceRuntime} from '../helpers/source-runtime.mjs';
import {onlineManager,QueryObserver} from '@tanstack/react-query';
const A='0000000001',B='0000000002';
const storedUserKey=readFileSync(new URL('../../src/lib/userDataCache.ts',import.meta.url),'utf8')
 .match(/const KEY = "([^"]+)"/)?.[1];
assert.ok(storedUserKey);
const r=()=>sourceRuntime({overrides:{'../hooks/useT':{useT:()=>key=>key},'../hooks/useInterfaceVariantSurface':{useInterfaceVariantSurface:group=>({variant:group+'-01',handlers:{},ref:null})},'../hooks/useDemoGenerationProjection':{useDemoGenerationProjection:()=>null}}});
for(const status of ['idle','loading','error','success'])test('Energy retains its full canonical structure with no data: '+status,()=>{
 const h=r(),Page=h.load('pages/index.tsx').default;
 const html=renderToStaticMarkup(React.createElement(Page,{snap:null,snapshotStatus:status,snapshotMode:'live'}));
 assert.match(html,/class="efhc-energy-stage"/);
 assert.match(html,/class="efhc-energy-progress-track"/);
 assert.match(html,/data-energy-chip-count="3"/);
 assert.doesNotMatch(html,/data-energy-state="(?:loading|recoverable-error)"/);
});
test('server correction is accepted immediately, even when lower than a local projection',()=>{
 const h=sourceRuntime();
 const {reconcileEnergyAnchor}=h.load('lib/energyProjection.ts');
 const a=reconcileEnergyAnchor({base_scaled:900n,base_client_ms:0},400n,1000);
 assert.equal(a.base_scaled,400n);assert.equal(a.base_client_ms,1000);
});
test('owner data persists across reload, while independent rejected updates retain it',async()=>{
 const h=sourceRuntime(),q=h.load('lib/queryClient.ts');
 assert.equal(typeof q.activateUserDataOwner,'function','explicit USER owner boundary is required');
 const c=q.createEfhcQueryClient();q.activateUserDataOwner(c,A,false);
 c.setQueryData(['panels',A,'summary'],{active_count:3});
 c.setQueryData(['referrals',A,'stats'],{active_referrals:4});
 await assert.rejects(c.fetchQuery({queryKey:['panels',A,'summary'],queryFn:()=>Promise.reject(Error('offline')),retry:false,staleTime:0}));
 const next=sourceRuntime({storage:h.storage}).load('lib/queryClient.ts'),reload=next.createEfhcQueryClient();next.activateUserDataOwner(reload,A,false);
 assert.equal(reload.getQueryData(['panels',A,'summary']).active_count,3);
 assert.equal(reload.getQueryData(['referrals',A,'stats']).active_referrals,4);
 c.clear();reload.clear();
});
test('USER switch clears former data and settings; late responses and return cannot restore them',()=>{
 const h=sourceRuntime(),q=h.load('lib/queryClient.ts');
 assert.equal(typeof q.activateUserDataOwner,'function');
 const c=q.createEfhcQueryClient();q.activateUserDataOwner(c,A,false);
 c.setQueryData(['panels',A,'summary'],{active_count:3});
 const settings=h.load('lib/settings.ts');settings.saveSettings({...settings.resetSettings(),lang:'ru',color_theme_id:'CT-03'});
 assert.equal(q.activateUserDataOwner(c,B,false),true);
 assert.equal(c.getQueryData(['panels',A,'summary']),undefined);
 assert.equal(settings.loadSettings().lang,'en');assert.equal(settings.loadSettings().color_theme_id,'CT-01');
 c.setQueryData(['panels',A,'summary'],{active_count:999});
 const next=sourceRuntime({storage:h.storage}).load('lib/queryClient.ts'),reload=next.createEfhcQueryClient();next.activateUserDataOwner(reload,B,false);
 assert.equal(reload.getQueryData(['panels',A,'summary']),undefined);
 q.activateUserDataOwner(c,A,false);assert.equal(c.getQueryData(['panels',A,'summary']),undefined);
 c.clear();reload.clear();
});
test('Admin Global ID selection does not reset USER cache or settings',()=>{
 const h=sourceRuntime(),q=h.load('lib/queryClient.ts');assert.equal(typeof q.activateUserDataOwner,'function');
 const c=q.createEfhcQueryClient();q.activateUserDataOwner(c,A,false);
 c.setQueryData(['panels',A,'summary'],{active_count:3});
 const settings=h.load('lib/settings.ts');settings.saveSettings({...settings.resetSettings(),lang:'ru'});
 assert.equal(q.activateUserDataOwner(c,B,true),false);
 assert.equal(c.getQueryData(['panels',A,'summary']).active_count,3);assert.equal(settings.loadSettings().lang,'ru');c.clear();
});
test('credentials and Admin permissions never enter the persisted USER read model',()=>{
 const h=sourceRuntime(),q=h.load('lib/queryClient.ts'),c=q.createEfhcQueryClient();q.activateUserDataOwner(c,A,false);
 c.setQueryData(['auth','session'],{token:'DO_NOT_PERSIST',roles:['superadmin']});
 c.setQueryData(['panels',A,'summary'],{active_count:2});
 assert.ok(![...h.storage.values()].join('').includes('DO_NOT_PERSIST'));c.clear();
});
test('unavailable storage cannot prevent the zero model or default settings',async()=>{
 const h=sourceRuntime();h.window.localStorage.getItem=()=>{throw Error('blocked');};h.window.localStorage.setItem=()=>{throw Error('blocked');};
 const q=h.load('lib/queryClient.ts'),c=q.createEfhcQueryClient();q.activateUserDataOwner(c,A,false);
 assert.equal(h.load('lib/browserFallback.ts').emptyOwnerSnapshot(A).profile.main_balance,'0.00000000');
 assert.equal((await h.load('lib/settings.ts').loadSettingsAsync()).lang,'en');c.clear();
});
test('offline backend mutations reject without pausing for automatic replay',{timeout:2000},async()=>{
 const q=sourceRuntime().load('lib/queryClient.ts'),c=q.createEfhcQueryClient();
 onlineManager.setOnline(false);
 try{const mutation=c.getMutationCache().build(c,{mutationFn:async()=>{throw Error('offline');}});await assert.rejects(mutation.execute(),/offline/);assert.equal(mutation.state.isPaused,false);}
 finally{onlineManager.setOnline(true);c.clear();}
});
test('all Admin GET views retain their operator-scoped data on transient failure, never on permission denial',async()=>{
 const h=sourceRuntime(),service=h.load('services/adminLinked.service.ts');
 assert.equal(typeof service.readAdminDisplay,'function','shared Admin read model is required');
 const read=service.readAdminDisplay;
 assert.equal((await read(A,'/admin/reports/overview',async()=>({amount:'12.00000000'}))).amount,'12.00000000');
 assert.equal((await read(A,'/admin/reports/overview',async()=>{throw Object.assign(Error('offline'),{status:503});})).amount,'12.00000000');
 await assert.rejects(read(B,'/admin/reports/overview',async()=>{throw Error('offline');}),/offline/);
 await assert.rejects(read(A,'/admin/reports/overview',async()=>{throw Object.assign(Error('denied'),{status:403});}),/denied/);
});
test('display Global ID and cached data are independent of transport credentials; changing USER owner replaces them',()=>{
 const h=sourceRuntime(),display=h.load('lib/displayOwner.ts'),auth=h.load('lib/auth-session.ts'),q=h.load('lib/queryClient.ts');
 assert.equal(typeof display.resolvedDisplayOwner,'function');
 const credential=token=>({access_token:token.repeat(40),token_type:'Bearer',expires_at:'2099-01-01T00:00:00Z'});
 auth.storeAuthSession(credential('A'));
 const c=q.createEfhcQueryClient();q.activateUserDataOwner(c,A,false);
 display.recordResolvedDisplayOwner(A);assert.equal(display.resolvedDisplayOwner(),A);
 auth.storeAuthSession(credential('B'));assert.equal(display.resolvedDisplayOwner(),A);
 auth.clearAuthSession();assert.equal(display.resolvedDisplayOwner(),A);
 c.setQueryData(['panels',A,'summary'],{active_count:3});display.beginDisplayOwnerResolution(true);
 assert.equal(display.resolvedDisplayOwner(),null);assert.equal(c.getQueryData(['panels',A,'summary']).active_count,3);
 display.recordResolvedDisplayOwner(A);assert.equal(display.resolvedDisplayOwner(),A);
 display.recordResolvedDisplayOwner(B);q.activateUserDataOwner(c,B,false);assert.equal(display.resolvedDisplayOwner(),B);
 assert.ok(![...h.storage.values()].join('').includes('A'.repeat(40)));c.clear();
});
test('two windows retain separate active owners, caches and settings over switches',t=>{
 const disk=new Map(),one=sourceRuntime({storage:disk}),two=sourceRuntime({storage:disk});
 const q1=one.load('lib/queryClient.ts'),q2=two.load('lib/queryClient.ts'),c1=q1.createEfhcQueryClient(),c2=q2.createEfhcQueryClient();
 t.after(()=>{c1.clear();c2.clear();});
 q1.activateUserDataOwner(c1,A,false);c1.setQueryData(['panels',A,'summary'],{active_count:3});
 const s1=one.load('lib/settings.ts');s1.saveSettings({...s1.resetSettings(),lang:'ru',color_theme_id:'CT-03'});
 q2.activateUserDataOwner(c2,B,false);c2.setQueryData(['panels',B,'summary'],{active_count:5});
 const s2=two.load('lib/settings.ts');s2.saveSettings({...s2.resetSettings(),lang:'en'});
 assert.equal(s1.loadSettings().lang,'ru');assert.equal(s1.loadSettings().color_theme_id,'CT-03');
 assert.equal(one.load('lib/userDataCache.ts').currentUserDataOwner(),A);
 q1.activateUserDataOwner(c1,'0000000003',false);
 assert.equal(two.load('lib/userDataCache.ts').currentUserDataOwner(),B);assert.equal(c2.getQueryData(['panels',B,'summary']).active_count,5);
 assert.equal(s2.loadSettings().lang,'en');c1.clear();c2.clear();
});
test('activity refreshes active data; online alone and repeated events never create a replay queue',async()=>{
 const h=sourceRuntime(),q=h.load('lib/queryClient.ts'),c=q.createEfhcQueryClient(),events=new EventTarget();
 const activity=h.load('lib/frontendActivity.ts');assert.equal(typeof activity.startActivitySync,'function');
 let calls=0;const observer=new QueryObserver(c,{queryKey:['activity-data'],queryFn:async()=>++calls,retry:false});
 const off=observer.subscribe(()=>{});await new Promise(r=>setTimeout(r,10));
 const stop=activity.startActivitySync(c,events),before=calls;
 try{
  events.dispatchEvent(new Event('online'));await new Promise(r=>setTimeout(r,10));assert.equal(calls,before);
  events.dispatchEvent(new Event('pointerdown'));await new Promise(r=>setTimeout(r,10));assert.equal(calls,before+1);
  events.dispatchEvent(new Event('keydown'));events.dispatchEvent(new Event('scroll'));await new Promise(r=>setTimeout(r,10));assert.equal(calls,before+1);
 }finally{stop();off();c.clear();}
});
test('cached Admin view permits reads, but a command only refreshes permission and never executes itself',async()=>{
 const h=sourceRuntime(),view=h.load('lib/adminViewState.ts');
 view.rememberAdminView(A);assert.equal(view.markAdminUnavailable(A),true);
 assert.equal(view.cachedAdminView(A),'readonly');
 let requests=0;
 assert.equal(await view.allowAdminCommand('/admin/bank/mint','POST',async()=>{requests++;return {global_id:A,role:'admin'};}),false);
 assert.equal(requests,1);assert.equal(view.cachedAdminView(A),'allowed');
 assert.equal(await view.allowAdminCommand('/admin/bank/mint','POST',async()=>{throw Error('must not refresh a confirmed view');}),true);
 view.markAdminUnavailable(A);
 await view.allowAdminCommand('/admin/bank/mint','POST',async()=>{throw Object.assign(Error('denied'),{status:403});});
 assert.equal(view.cachedAdminView(A),null);assert.equal(view.cachedAdminView(B),null);
});
test('drafts survive reload as text only and reset for a new USER without clearing another window',()=>{
 const disk=new Map(),one=sourceRuntime({storage:disk}),two=sourceRuntime({storage:disk});
 const d1=one.load('lib/ownerDrafts.ts'),d2=two.load('lib/ownerDrafts.ts');
 d1.writeOwnerDraft(A,'exchange.amount','12.345');d2.writeOwnerDraft(B,'exchange.amount','77');
 assert.equal(sourceRuntime({storage:disk,session:one.session}).load('lib/ownerDrafts.ts').readOwnerDraft(A,'exchange.amount'),'12.345');
 d1.resetWindowDrafts(B);assert.equal(d1.readOwnerDraft(B,'exchange.amount'),null);
 assert.equal(d2.readOwnerDraft(B,'exchange.amount'),'77');
 assert.equal(d1.readOwnerDraft(null,'exchange.amount'),null);
});

test('a fresh browser tab restores device-only view choices but never unlocks a previous owner',()=>{
 const disk=new Map(),first=sourceRuntime({storage:disk}),q=first.load('lib/queryClient.ts'),c=q.createEfhcQueryClient();
 q.activateUserDataOwner(c,A,false);
 c.setQueryData(['panels',A,'summary'],{active_count:9});
 const settings=first.load('lib/settings.ts');
 settings.saveSettings({...settings.resetSettings(),lang:'ru',color_theme_id:'CT-03',music_enabled:true});
 const device=disk.get('EFHC_DEVICE_VIEW_PREFERENCES');
 assert.ok(device?.includes('CT-03'));
 assert.ok(!device.includes(A) && !device.includes('access_token') && !device.includes('balance'));
 const second=sourceRuntime({storage:disk,session:new Map()});
 const preferences=second.load('lib/settings.ts').loadSettings();
 assert.equal(preferences.lang,'ru');assert.equal(preferences.color_theme_id,'CT-03');
 assert.equal(preferences.music_enabled,true);
 assert.equal(second.load('lib/displayOwner.ts').resolvedDisplayOwner(),null);
 const reload=second.load('lib/queryClient.ts'),client=reload.createEfhcQueryClient();
 assert.equal(client.getQueryData(['panels',A,'summary']),undefined);
 reload.activateUserDataOwner(client,A,false);
 assert.equal(client.getQueryData(['panels',A,'summary']).active_count,9);
 client.clear();c.clear();
});
test('new tab never adopts a previous owner avatar through unscoped legacy preferences',()=>{
 const disk=new Map(),first=sourceRuntime({storage:disk});
 const settings=first.load('lib/settings.ts');
 const legacy={...settings.resetSettings(),lang:'ru',color_theme_id:'CT-05',
   avatar_source:'social',avatar_social_provider:'telegram',
   avatar_social_url:'https://example.org/person.jpg',
   avatar_custom_images:['data:image/png;base64,ZmFrZQ=='],
   avatar_url:'data:image/png;base64,ZmFrZQ=='};
 disk.set('EFHC_USER_SETTINGS_V1',JSON.stringify(legacy));
 const second=sourceRuntime({storage:disk,session:new Map()});
 const recovered=second.load('lib/settings.ts').loadSettings();
 assert.equal(recovered.lang,'ru');
 assert.equal(recovered.color_theme_id,'CT-05');
 assert.equal(recovered.avatar_source,'telegram');
 assert.equal(recovered.avatar_url,null);
 assert.equal(recovered.avatar_social_url,null);
 assert.deepEqual(recovered.avatar_custom_images,[]);
});
test('verified same-owner marker with empty tab entries recovers durable display data',()=>{
 const disk=new Map(),first=sourceRuntime({storage:disk}),q=first.load('lib/queryClient.ts'),c=q.createEfhcQueryClient();
 q.activateUserDataOwner(c,A,false);
 c.setQueryData(['panels',A,'summary'],{active_count:4});
 c.clear();
 const session=new Map([[storedUserKey,JSON.stringify({owner:A,entries:[]})]]);
 const second=sourceRuntime({storage:disk,session}),reload=second.load('lib/queryClient.ts'),client=reload.createEfhcQueryClient();
 reload.activateUserDataOwner(client,A,false);
 assert.equal(client.getQueryData(['panels',A,'summary']).active_count,4);
 client.clear();
});
test('explicit sign-out forgets personal snapshots but preserves generic appearance',()=>{
 const disk=new Map(),h=sourceRuntime({storage:disk}),q=h.load('lib/queryClient.ts'),c=q.createEfhcQueryClient();
 q.activateUserDataOwner(c,A,false);
 c.setQueryData(['panels',A,'summary'],{active_count:2});
 const settings=h.load('lib/settings.ts');
 settings.saveSettings({...settings.resetSettings(),lang:'ru',color_theme_id:'CT-03'});
 assert.ok(disk.has(storedUserKey+':'+A));
 q.forgetSignedOutUser(c);
 assert.equal(c.getQueryData(['panels',A,'summary']),undefined);
 assert.ok(!disk.has(storedUserKey+':'+A));
 assert.equal(h.load('lib/userDataCache.ts').currentUserDataOwner(),null);
 assert.equal(sourceRuntime({storage:disk,session:new Map()}).load('lib/settings.ts').loadSettings().color_theme_id,'CT-03');
 c.clear();
});
test('embedded locale dictionaries allow immediate shell while network locale refresh is pending',()=>{
 const app=readFileSync(new URL('../../src/pages/_app.tsx',import.meta.url),'utf8');
 assert.match(app,/setUiDictLoaded\] = useState\(true\)/);
 assert.match(app,/setRuDictLoaded\] = useState\(true\)/);
 assert.match(app,/setDescDictLoaded\] = useState\(true\)/);
 assert.doesNotMatch(app,/setUiDictLoaded\(false\)|setRuDictLoaded\(false\)|setDescDictLoaded\(false\)/);
 assert.match(app,/setUiDict\(fallback\)/);
});
