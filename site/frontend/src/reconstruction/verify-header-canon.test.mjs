import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname,resolve } from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const read=(path)=>readFileSync(resolve(root,path),'utf8');
const header=read('src/components/GlobalHeader.tsx');
const css=read('src/styles/header-layout.css');
const app=read('src/pages/_app.tsx');
const shell=read('src/components/Layout.tsx');

test('four visible user actions remain in frozen v866 order with real callbacks',()=>{
  assert.deepEqual([...header.matchAll(/data-action="(FAQ|Wallet|Deposit|HUB)"/g)].map(x=>x[1]),['FAQ','Wallet','Deposit','HUB']);
  assert.match(header,/onClick=\{onFaq\}/);
  assert.match(header,/onClick=\{props\.onOpenWallet\}/);
  assert.match(header,/onClick=\{onDepositClick\}/);
  assert.match(header,/onClick=\{onHub\}/);
  // Superseded by OWNER cycle 0008: no fifth Admin action in ANY mode.
  assert.match(header,/data-action-count="4"/);
  assert.doesNotMatch(header,/showAdminEntry|onModeSwitch/);
});
test('only approved Header geometry is scoped to User and only cycle 0007',()=>{
  assert.match(header,/data-canon-header="true"/);
  assert.match(css,/\[data-interface-app-mode="user"\]/);
  assert.match(css,/\[data-canon-header="true"\]/);
  assert.match(shell,/data-efhc-canon-migration=\{appMode === "user" \? "v872" : undefined\}/);
  assert.doesNotMatch(css,/\.efhc-admin|data-interface-app-mode="admin"/);
  assert.match(app,/import "\.\.\/styles\/header-layout\.css";/);
});
test('frozen TZ-002 equal columns and four buttons persist across 320-430',()=>{
  assert.match(css,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\) !important;/);
  assert.match(css,/grid-template-columns:repeat\(4,minmax\(0,1fr\)\) !important;/);
  assert.match(css,/\[data-action-count="4"\] \.efhc-header-action span \{\s*display:inline;/);
  assert.match(css,/@media\(max-width:430px\)/);
  assert.match(css,/max-width:none !important;/);
});
test('Header font/status geometry is carried directly from approved v866',()=>{
  for(const exact of ['font-family:Inter,ui-sans-serif,system-ui','font-size:.875rem','font-weight:800','font-size:.64rem','font-size:.59rem','width:2.35rem','height:2.35rem'])assert.ok(css.includes(exact),exact);
  assert.match(css,/gap:\.38rem !important;/);
  assert.match(css,/font-size:\.75rem !important;/);
});
test('D8 value never changes or strips trailing zeros; density fit measured rather than rounded',()=>{
  assert.match(header,/sumScaledDown\(props\.mainBalance, props\.bonusBalance, 8\)/);
  assert.match(header,/\{displayedTotal\}/);
  assert.match(header,/useMeasuredBalanceFont\(displayedTotal\)/);
  assert.match(css,/font-variant-numeric:tabular-nums lining-nums/);
  assert.match(css,/--efhc-header-balance-fit-size,13px/);
  assert.doesNotMatch(header,/parseFloat\(props\.(?:mainBalance|bonusBalance)\)/);
});
test('theme variant ownership remains HS/SC/HB and CT colors are not replaced',()=>{
  assert.match(header,/data-hs=\{headerComposition\.shell\}/);
  assert.match(header,/data-sc=\{headerComposition\.statuses\}/);
  assert.match(header,/data-hb=\{headerComposition\.balance\}/);
  assert.match(css,/--efhc-color-accent-soft/);
  assert.doesNotMatch(css,/\[data-color-theme-id=|--efhc-color-accent:\s*#[0-9a-f]{6}/i);
});
test('avatar/name actions and owner statuses remain functional',()=>{
  assert.match(header,/className="efhc-game-header_profile-avatar-button"\s*onClick=\{props\.onAvatar\}/);
  assert.match(header,/className="efhc-game-header_profile-name-button"\s*onClick=\{props\.onAvatar\}/);
  assert.match(header,/<StatusIndicator\s+kind="activ"\s+active=\{props\.hasActiv\}/);
  assert.match(header,/<StatusIndicator\s+kind="vip"\s+active=\{props\.isVip\}/);
});
