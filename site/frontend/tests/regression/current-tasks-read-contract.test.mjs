import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceRuntime} from '../helpers/source-runtime.mjs';
function service(payload){return sourceRuntime({overrides:{'../lib/api':{apiRequest:async()=>payload}}}).load('services/tasks.service.ts');}
const item=bonus=>({id:'1',code:'TASK_PUBLIC_TEST',title:'Task',bonus_efhc:bonus,is_active:true});
for(const invalid of ['0E-8','1e-3','NaN','1.123456789']){
 test('invalid task amount is rejected before React render: '+invalid,async()=>{
  await assert.rejects(service({items:[item(invalid)]}).getTasksCatalog());
  await assert.rejects(service({total_bonus_earned:invalid}).getTaskEarnings());
  await assert.rejects(service({items:[{id:null,task_id:'1',status:'not_started',bonus_efhc:invalid,can_claim:false}]}).getMyTasks());
 });
}
test('valid zero and large task D8 values remain exact strings',async()=>{
 for(const value of ['0.00000000','9007199254740993.12345678']){
  assert.equal((await service({items:[item(value)]}).getTasksCatalog())[0].bonus_efhc,value);
  assert.equal((await service({total_bonus_earned:value}).getTaskEarnings()).total_bonus_earned,value);
 }
});
test('bad catalog synchronization preserves the previous validated catalog',async()=>{
 let payload={items:[item('0.00000000')]};
 const h=sourceRuntime({overrides:{'../lib/api':{apiRequest:async()=>payload}}}),c=h.load('lib/queryClient.ts').createEfhcQueryClient();
 const s=h.load('services/tasks.service.ts'),options={queryKey:['tasks-catalog'],queryFn:s.getTasksCatalog,retry:false,staleTime:0};
 try{await c.fetchQuery(options);payload={items:[item('0E-8')]};await assert.rejects(c.fetchQuery(options));assert.equal(c.getQueryData(options.queryKey)[0].bonus_efhc,'0.00000000');}finally{c.clear();}
});

test('actual Tasks observers reject old malformed cached amounts before the formatter',async()=>{
 const {QueryClient,QueryObserver}=await import('@tanstack/react-query');
 const h=sourceRuntime({overrides:{
  '../lib/api':{apiRequest:async()=>({})},
  '../auth/AuthSessionProvider':{useAuthOwnerGlobalId:()=> '0000000088'},
  '@tanstack/react-query':{useQuery:options=>options,useMutation:()=>({}),useQueryClient:()=>({})},
 }});
 const hooks=h.load('queries/useTasks.ts'),c=new QueryClient();
 const cases=[
  [hooks.useTasksCatalog(),[item('0E-8')]],
  [hooks.useMyTasks(),[{id:null,task_id:'1',status:'not_started',bonus_efhc:'0E-8',can_claim:false}]],
  [hooks.useTaskEarnings(),{total_bonus_earned:'0E-8',bonus_asset:'EFHCb',includes_ads:true}],
 ];
 try{for(const [options,data] of cases){
  c.setQueryData(options.queryKey,data);const observer=new QueryObserver(c,{...options,enabled:false});
  const result=observer.getCurrentResult();assert.equal(result.data,undefined,'bad cached data never reaches Tasks render');assert.equal(result.isError,true);
  observer.destroy();
 }}finally{c.clear();}
});

test("Claimed task bonus refreshes account balances; a failed read never reports the paid claim as failed", async () => {
  const invalidations = [];
  const h = sourceRuntime({overrides:{
    "@tanstack/react-query":{
      useMutation: options => options,
      useQuery: options => options,
      useQueryClient: () => ({ invalidateQueries: options => {
        invalidations.push(options);
        return options.queryKey[0] === "accountBalance" ? Promise.reject(new Error("offline read")) : Promise.resolve();
      }}),
    },
    "../auth/AuthSessionProvider": {useAuthOwnerGlobalId:()=> "0000000088"},
    "../services/tasks.service":{
      claimTask: () => {},getMyTasks:()=>{},getTaskEarnings:()=>{},getTasksCatalog:()=>{},
      selectTaskCatalog:()=>{},selectMyTasks:()=>{},selectTaskEarnings:()=>{},
    },
  }});
  const mutation = h.load("queries/useTasks.ts").useClaimTask();
  await assert.doesNotReject(mutation.onSuccess());
  assert.ok(invalidations.some(options => options.queryKey[0] === "accountBalance" && options.queryKey[1] === "0000000088"));
  assert.ok(invalidations.some(options => options.queryKey[0] === "tasksMy"));
  assert.ok(invalidations.some(options => options.queryKey[0] === "tasksEarnings"));
});
test("Task catalog is persisted as a public catalog without persisting personal balances", () => {
  const file = readFileSync(fileURLToPath(new URL("../../src/lib/publicCatalogPersistence.ts",import.meta.url)),"utf8");
  assert.match(file, /key\.length === 1 && key\[0\] === "tasksCatalog"/);
  assert.doesNotMatch(file, /key\[0\] === "accountBalance"/);
});
