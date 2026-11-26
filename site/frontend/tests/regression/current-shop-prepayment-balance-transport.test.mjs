import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {stripTypeScriptTypes} from "node:module";
import test from "node:test";
const source=new URL("../../src/services/browserShopPrepayment.service.ts",import.meta.url);
const review=new URL("../features/browser-shop/shopCheckoutReview.ts",source);
function codeToUrl(src) {
  return "data:text/javascript;base64," + Buffer.from(src).toString("base64");
}
let sourceCode=stripTypeScriptTypes(readFileSync(source,"utf8"))
  .replace('"../features/browser-shop/shopCheckoutReview"',JSON.stringify(review.href))
  .replace('"../lib/api"',JSON.stringify(codeToUrl("export const apiRequest=(...args)=>globalThis.syntheticShopBalanceTransport.call(...args)")))
  .replace('"../lib/auth-session"',JSON.stringify(codeToUrl("export const getAuthAuthorizationHeader=()=>globalThis.syntheticShopBalanceTransport.authorization")))
  .replace('"../lib/api/generated/economicUserSeamValidators"',JSON.stringify(codeToUrl("export const parseBrowserShopCreateIntentResponse=(r)=>r")))
  .replace('"../types/db-id"',JSON.stringify(codeToUrl("export const dbIdFromApi=(x)=>{if(!/^[1-9][0-9]*$/.test(x))throw new TypeError('ID');return String(x)}")));
const {callShopPrepayment:call}=await import(codeToUrl(sourceCode));
const key="opaque-same-verified-request";
const selection={sku:"EFHC_VIP_NFT_ANY",method:"EFHC",quantity:1,custom_efhc_amount_d8:null};
const token="synthetic-handoff";
const reviewId="a".repeat(64);
const prepared={review_id:reviewId,quote:{asset:"EFHC",amount:"500.00000000"}};
const paid={state:"paid",order_id:"991"};
test("signed handoff alone cannot debit; verified bearer remains canonical transport responsibility",async()=>{
  let count=0;
  globalThis.syntheticShopBalanceTransport={authorization:"",call:async()=>{count++;return paid}};
  await assert.rejects(call("pay",token,key,selection,prepared),/NATIVE_SESSION_REQUIRED/);
  assert.equal(count,0);
  globalThis.syntheticShopBalanceTransport.authorization="Bearer synthetic-native-bearer";
  globalThis.syntheticShopBalanceTransport.call=async(path,method,options)=>{
    assert.equal(path,"/shopfront/checkout-requests/pay-balance");
    assert.equal(method,"POST");
    assert.deepEqual(options.headers,{"X-EFHC-Handoff":token});
    assert.deepEqual(options.body,{key,...selection,review_id:reviewId});
    return paid;
  };
  const result=await call("pay",token,key,selection,prepared);
  assert.equal(result.order_id,"991");
  assert.equal(result.payment,null);
});
test("paid replay has no signing envelope, and status cannot route into balance Pay",async()=>{
  const requests=[];
  globalThis.syntheticShopBalanceTransport={authorization:"Bearer synthetic",call:async(path,_method,options)=>{
    requests.push([path,options.body]);return paid;
  }};
  assert.equal((await call("status",token,key)).payment,null);
  assert.deepEqual(requests,[["/shopfront/checkout-requests/status",{key}]]);
  for (const malformed of [{state:"paid"},{...paid,intent_id:"992"},{...paid,payment:{}},{state:"issued",order_id:"991"}]) {
    globalThis.syntheticShopBalanceTransport.call=async()=>malformed;
    await assert.rejects(call("pay",token,key,selection,prepared),/BALANCE_RESPONSE_INVALID/);
  }
});
