import test from "node:test";
import assert from "node:assert/strict";
import {readdirSync,readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import path from "node:path";

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const roots=["src/styles","public"];
const dead=/\.efhc-error-page\b|\.efhc-safe-error-state\b|\[data-safe-error-state\]|#errorPage\b/;
const enumerate=(dir)=>readdirSync(dir,{recursive:true,withFileTypes:true})
  .filter(entry=>entry.isFile() && entry.name.endsWith(".css"))
  .map(entry=>path.join(entry.parentPath||entry.path,entry.name));

test("No retired 404/500/error route CSS ships from app styles or public assets",()=>{
  const files=roots.flatMap(root=>enumerate(path.join(frontend,root)));
  assert.ok(files.length>=45,"Full exported CSS inventory must be scanned");
  const violations=[];
  for(const filename of files){
    const text=readFileSync(filename,"utf8");
    if(dead.test(text)) violations.push(path.relative(frontend,filename));
  }
  assert.deepEqual(violations,[],"Retired user error screens must be removed from CSS, not merely hidden");
});

test("Approved live USER and Shop selectors survive error-screen CSS retirement",()=>{
  const globalCss=readFileSync(path.join(frontend,"src/styles/globals.css"),"utf8");
  const shopCss=readFileSync(path.join(frontend,"public/SHOP_v866.css"),"utf8");
  const referralsCss=readFileSync(path.join(frontend,"public/referrals.css"),"utf8");
  assert.match(globalCss,/\.efhc-withdraw-create-card/);
  assert.match(shopCss,/\.efhc-ads-trust-shell/);
  assert.match(referralsCss,/\.efhc-referrals-shell/);
  // Domain-specific inline errors are still required for truthful operation feedback.
  assert.match(globalCss,/\.efhc-safe-error-inline/);
});
