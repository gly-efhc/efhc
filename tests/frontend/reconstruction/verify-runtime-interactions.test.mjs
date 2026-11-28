import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import vm from "node:vm";
const read = (p) => readFileSync(new URL(p, sourceUrl), "utf8");

test("theme template selection is never mislabeled aria-disabled", () => {
  for (const name of ["useInterfaceVariantSurface", "useGlobalThemeSurface"]) {
    const text = read(`../${name === "useGlobalThemeSurface" ? "hooks" : "hooks"}/${name}.ts`);
    assert.doesNotMatch(text, /"aria-disabled":\s*active/);
    assert.match(text, /"data-interface-selection-active": active \? "true" : undefined/);
    assert.match(text, /customization\.(next|nextGlobalTheme)\(/);
  }
});
test("the historical theme disabled rule stays available ONLY for disabled elements", () => {
  const css = read("../styles/globals.css");
  assert.match(css, /:disabled,\[aria-disabled="true"\],\[data-disabled="true"\]/);
  const hooks = ["../hooks/useInterfaceVariantSurface.ts", "../hooks/useGlobalThemeSurface.ts"];
  for (const path of hooks) assert.doesNotMatch(read(path), /"aria-disabled"/);
});
test("PWA status is mounted headless; runtime registration remains", () => {
  const app = read("../pages/_app.tsx");
  const pwa = read("../components/PwaRuntimeStatus.tsx");
  assert.match(app, /<PwaRuntimeStatus t=\{t\} enabled=\{browserSupportsServiceWorker\(\)\} headless \/>/);
  assert.match(pwa, /void props\.headless;\s*void props\.t;\s*return null;/);
  assert.match(pwa, /navigator\.serviceWorker\.register/);
  // OWNER 14.11.2026: Serwist is the sole cache engine.
  assert.doesNotMatch(pwa, /SET_CACHE_POLICY|resolveAdaptiveCachePolicy/);
  assert.match(pwa, /type:"CACHE_URLS",payload:\{urlsToCache\}/);
});
test("Back routing removes stale repeated Pages path prefixes", () => {
  const src = read("../lib/appBackNavigation.ts");
  assert.match(src, /import \{withoutAppBasePath\} from "\.\/appBasePath"/);
  assert.match(src, /const canonical = withoutAppBasePath\(route\)/);
  assert.match(src, /rememberRoute\(routerRef\.current/);
  assert.match(src, /router\.events\.on\("routeChangeComplete"/);
  assert.match(src, /writeRouteStack\(index >= 0 \? stack\.slice\(0, index \+ 1\) : \[target\]\);\s*return router\.replace\(target, undefined, \{ scroll: false \}\)/);
});
test("Pages prefix migration executes the real shared normalizer; release paths remain untouched", () => {
  const require = createRequire(new URL("../../../frontend/package.json", import.meta.url));
  let ts;
  try { ts = require("typescript"); }
  catch { ts = require(join(execFileSync("npm", ["root", "-g"], {encoding:"utf8"}).trim(), "typescript")); }
  const js = ts.transpileModule(read("../lib/appBasePath.ts"), {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
  const load = (env) => { const exports = {}; vm.runInNewContext(js, {exports, process:{env}}); return exports; };
  const pages = load({NEXT_PUBLIC_EFHC_PAGES_PREVIEW:"1", NEXT_PUBLIC_EFHC_BASE_PATH:"/efhc"});
  for (const [input, expected] of [["/efhc/efhc/panels", "/panels"], ["/Test-3/efhc/faq?item=2", "/faq?item=2"], ["/efhc", "/"], ["/efhc-other/panels", "/efhc-other/panels"]]) {
    assert.equal(pages.withoutAppBasePath(input), expected);
  }
  const release = load({NEXT_PUBLIC_EFHC_PAGES_PREVIEW:"0", NEXT_PUBLIC_EFHC_BASE_PATH:"/efhc"});
  assert.equal(release.withoutAppBasePath("/efhc/panels"), "/efhc/panels");
  const invalid = load({NEXT_PUBLIC_EFHC_PAGES_PREVIEW:"1", NEXT_PUBLIC_EFHC_BASE_PATH:"/../x"});
  assert.throws(() => invalid.appBasePath(), /Invalid configured Pages basePath/);
});
test("modal pointer dragging clamps to visual viewport with keyboard", () => {
  const src = read("../components/ui/Modal.tsx");
  assert.match(src, /window\.visualViewport\?\.offsetTop/);
  assert.match(src, /viewportBottom - rect\.bottom/);
  assert.match(src, /onPointerCancel=\{onDragEnd\}/);
  assert.match(src, /onClick=\{props\.onClose\}/);
});
test("OWNER approved Energy page and financial MAX CTA retained", () => {
  assert.match(read("../pages/index.tsx"), /efhc-energy/);
  assert.match(read("../components/ExchangePanel.tsx"), /data-exchange-max-action="true"/);
  assert.match(read("../pages/withdraw.tsx"), /efhc-withdraw-max-cta/);
  assert.match(read("../pages/panels.tsx"), /panels/);
  assert.match(read("../pages/referrals.tsx"), /referrals/);
});
test("no direct production finances or admin authorization mutation", () => {
  const pwa = read("../components/PwaRuntimeStatus.tsx");
  assert.doesNotMatch(pwa, /tonProof\s*=|sendTransaction\s*\(/);
  assert.match(read("../lib/appBackNavigation.ts"), /APP_BACK_NAVIGATION_CONTRACT/);
});
