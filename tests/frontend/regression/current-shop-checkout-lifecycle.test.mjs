import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
const lifecycleUrl = new URL("../../../frontend/src/features/browser-shop/shopCheckoutLifecycle.ts", import.meta.url);
const reviewUrl = new URL("./shopCheckoutReview.ts", lifecycleUrl);
const lifecycleCode = stripTypeScriptTypes(readFileSync(lifecycleUrl, "utf8"))
  .replace('"./shopCheckoutReview"', JSON.stringify(reviewUrl.href));
const {acceptShopReply: accept, mayStartAnotherShopRequest: free, openShopSession: open,
  planShopAction: plan, restoreShopSession: restore, showShopModal: show} =
  await import("data:text/javascript;base64," + Buffer.from(lifecycleCode).toString("base64"));
const preparedReply = { state:"prepared", review_id:"a".repeat(64), quote:{ asset:"TON",amount:"1.25" } };

const key = "synthetic-same-attempt";
const dispatch = (s, a, reply, extra={}) => {
  const {session,command}=plan(s,a,{explicit:true,...extra});
  assert.ok(command);
  assert.equal(command.key,key);
  return accept(session,command,reply);
};
const prepare = () => dispatch(open(key),"prepare",preparedReply,{freshUndispatched:true});

test("closing any modal presentation does not create a command; explicit cancel only for known prepared request", () => {
  const prepared=prepare(), closed=show(prepared,false);
  assert.equal(closed.authoritative,"prepared");
  assert.equal(plan(closed,"cancel",{explicit:true}).command,null);
  assert.equal(free(closed),false);
  const reopened=show(closed,true);
  assert.equal(plan(reopened,"cancel",{explicit:false}).command,null);
  assert.equal(free(dispatch(reopened,"cancel",{state:"canceled"})),true);
});
test("ambiguous prepare or cancel and not_seen retain same key and block a new payment", () => {
  for (const [state,action,extras] of [[open(key),"prepare",{freshUndispatched:true}],[prepare(),"cancel",{}]]) {
    const unknown=dispatch(state,action,null,extras);
    const delayed=dispatch(unknown,"status",{state:"not_seen"});
    assert.equal(delayed.key,key);
    assert.equal(free(delayed),false);
    assert.equal(plan(delayed,"pay",{explicit:true,wirePayVerified:true}).command,null);
    assert.equal(plan(delayed,"prepare",{explicit:true,freshUndispatched:true}).command,null);
  }
});
test("unverified Pay fails closed, fresh explicit permitted contract issues once; status replay never schedules a command", () => {
  const ready=prepare();
  assert.equal(plan(ready,"pay",{explicit:true}).command,null);
  const issued=dispatch(ready,"pay",{state:"issued",order_id:"71",intent_id:"81"},{wirePayVerified:true});
  assert.equal(plan(show(issued,true),"cancel",{explicit:true}).command,null);
  assert.equal(plan(issued,"pay",{explicit:true,wirePayVerified:true}).command,null);
  const mismatch=dispatch(issued,"status",{state:"paid",order_id:"72",intent_id:"82"});
  assert.equal(mismatch.authoritative,"issued");
  const paid=dispatch(issued,"status",{state:"paid",order_id:"71",intent_id:"81"});
  assert.equal(paid.refs.order_id,"71");
  assert.ok(free(paid));
  assert.equal(plan(paid,"cancel",{explicit:true}).command,null);
});
test("older operation replies cannot apply to a newer cancel or another owner attempt", () => {
  const ready=prepare(), status=plan(ready,"status",{explicit:false});
  const stillReady=accept(status.session,status.command,preparedReply);
  const cancel=plan(stillReady,"cancel",{explicit:true});
  assert.equal(accept(cancel.session,status.command,{state:"paid",order_id:"80"}),cancel.session);
  const different=plan(open("other-attempt"),"status",{explicit:false});
  assert.equal(accept(different.session,cancel.command,{state:"canceled"}),different.session);
});

test("a stale prepared snapshot after uncertain final action cannot re-enable Pay or Cancel", () => {
  for (const action of ["pay","cancel"]) {
    const unknown=dispatch(prepare(),action,null,{wirePayVerified:true});
    const stale=dispatch(unknown,"status",preparedReply);
    assert.equal(plan(stale,"pay",{explicit:true,wirePayVerified:true}).command,null);
    assert.equal(plan(stale,"cancel",{explicit:true}).command,null);
    assert.equal(free(stale),false);
  }
});

test("reload of ambiguous Pay permits status only, even when stale prepared replies arrive", () => {
  const reopened=show(restore(key,"pay"),true);
  const stale=dispatch(reopened,"status",preparedReply);
  assert.equal(plan(stale,"pay",{explicit:true,wirePayVerified:true}).command,null);
  assert.equal(plan(stale,"cancel",{explicit:true}).command,null);
  assert.equal(free(stale),false);
});

test("prepared status with missing/malformed quote cannot enable Pay; exact quote can restore", () => {
  for (const malformed of [{state:"prepared"}, {...preparedReply,review_id:"short"},
      {...preparedReply,quote:{asset:"USDT",amount:"1e-6"}}]) {
    const state = dispatch(show(restore(key,null),true),"status",malformed);
    assert.equal(state.review,null);
    assert.equal(plan(state,"pay",{explicit:true,wirePayVerified:true}).command,null);
  }
  const restored = dispatch(show(restore(key,null),true),"status",preparedReply);
  assert.equal(restored.review.quote.amount,"1.25");
  assert.equal(restored.review.review_id,"a".repeat(64));
  assert.ok(plan(restored,"pay",{explicit:true,wirePayVerified:true}).command);
});
