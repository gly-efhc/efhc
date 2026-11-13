import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";

const existing = path => existsSync(new URL(path,import.meta.url));
const source = path => readFileSync(new URL(path,import.meta.url),"utf8");

test("OWNER-retired technical pages are physically absent from current source",()=>{
  for(const path of [
    "../../src/pages/dev",
    "../../public/dev",
    "../../src/pages/404.tsx",
    "../../src/pages/500.tsx",
    "../../src/pages/_error.tsx",
    "../../src/components/ui/SafeErrorState.tsx",
    "../../src/components/QuietPageSurface.tsx",
    "../../src/components/ErrorBoundary.tsx",
  ]){
    assert.equal(existing(path),false,"Retired source still exists: "+path);
  }
});

test("App mounts real USER/Admin/Shop routes, with no fatal page replacement",()=>{
  const app=source("../../src/pages/_app.tsx");
  assert.doesNotMatch(app,/ErrorBoundary|QuietPageSurface|SafeErrorState/);
  assert.match(app,/<Component/);
  assert.match(app,/<AdminVisualProofRouter/);
  assert.match(app,/<ShopLayout/);
  assert.match(app,/<Layout/);
});

test("PWA never intercepts retired routes with synthetic 404 pages",()=>{
  const worker=source("../../public/sw.js");
  assert.doesNotMatch(worker,/isRetiredRoute|QuietPageSurface|SafeErrorState/);
  assert.ok(!worker.includes('event.respondWith(new Response("", {status: 404'));
  assert.match(worker,/purgeSupersededHtml/);
  assert.match(worker,/previousBuildCachesAtActivation/);
});

test("The actual Withdraw page is retained in the tree for data-safe rendering",()=>{
  const page=source("../../src/pages/withdraw.tsx");
  assert.match(page,/data-public-surface="withdraw"/);
  assert.match(page,/efhc-withdraw-create-card/);
  assert.match(page,/withdraw.my_requests/);
  assert.doesNotMatch(page,/QuietPageSurface/);
});
