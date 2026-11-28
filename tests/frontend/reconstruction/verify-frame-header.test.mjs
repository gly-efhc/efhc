import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const root = resolve(sourceDir, '../..');
const load = (path) => readFileSync(resolve(root, path), 'utf8');
const css = load('src/styles/header-frames.css');
const header = load('src/components/GlobalHeader.tsx');
const shell = load('src/components/ui/GameShell.tsx');
const card = load('src/components/ui/Card.tsx');
const app = load('src/pages/_app.tsx');
const profile = load('src/features/profile/WebProfilePage.tsx');

test('frozen v866 HTML remains external, pinned by source SHA', () => {
  assert.match(css, /9b6371f5fb62939596b78206f95031c447e9f2b375e62b30704403bb25102aef/);
  assert.doesNotMatch(css, /@import\s+url\(/);
  assert.doesNotMatch(css, /https?:\/\//);
});
test('canonical Header family, name size/weight and statuses are defined', () => {
  for (const marker of ['Inter,ui-sans-serif,system-ui','font-size:.875rem','font-weight:800','font-size:.64rem','font-size:.59rem','font-size:max(.75rem,12px)']) {
    assert.ok(css.includes(marker), marker);
  }
  assert.match(header, /className="profile-name"/);
  assert.doesNotMatch(header, /profile-name truncate text-sm font-bold/);
});
test('four Header actions; Profile Admin entry is role-gated and Account entry remains reachable', () => {
  // Current OWNER decision cycle 0008 supersedes temporary fifth Admin cell.
  assert.match(header, /data-action-count="4"/);
  assert.doesNotMatch(header, /showAdminEntry|onModeSwitch/);
  assert.match(profile, /\{ctx\.canRenderAdminPage \|\| ctx\.isAdmin \? \([\s\S]*?onClick=\{\(\) => void router\.push\("\/admin"\)\}[\s\S]*?\) : null\}/);
  assert.match(profile, /data-provider-entry="profile-footer"[\s\S]*?onClick=\{\(\) => setTab\("providers"\)\}/);
  const layout = load('src/components/Layout.tsx');
  assert.match(layout, /const canRenderAdminPage = Boolean\(props\.isAdmin\) \|\| \(\s*isDemoBackendMode\(\) && authSession\.status === "authenticated" &&\s*authSession\.context\?\.roles\.includes\("test_visual"\) === true\s*\)/);
  assert.match(layout, /isAdminRoute && !canRenderAdminPage/);
  assert.match(app, /fetchAdminAccess\(\)/);
});
test('shared real React templates retain their preexisting classes and add canon markers', () => {
  for(const id of ['source-game-hero','source-stats','source-stat','source-card','source-notice']) {
    assert.ok(shell.includes(`data-canon-frame="${id}"`), id);
  }
  assert.match(shell, /data-canon-template="v866"/);
  assert.match(shell, /className=\{`efhc-game-hero /);
  assert.match(card, /data-canon-frame="source-card"/);
});
test('current USER styles load after compiled CSS and remain separate from Admin and Shop', () => {
  // Current cascade: one compiled entry, then scoped USER links, then shared adapters.
  // This is a source-order guard, not a claim of historical HTML parity (Q1062).
  assert.match(app, /import "\.\.\/styles\/globals\.css";/);
  const userBlock = app.match(/\{!isAdminRoute && !isBrowserShop \? \(\s*<>([\s\S]*?)<\/>\s*\) : null\}/)?.[1];
  assert.ok(userBlock, 'USER-only stylesheet branch');
  const links = [...userBlock.matchAll(/\/([^/]+\.css)`/g)].map(m => m[1]);
  assert.deepEqual(links, ['FRONTEND_v866.css', 'responsive-layout.css', 'user-shell.css', 'react-viewport.css', 'exchange-withdraw-material.css', 'referrals.css', 'progress-models.css']);
  const adapter = app.indexOf('/react-runtime-layout.css');
  assert.ok(adapter > app.indexOf('/progress-models.css'));
  assert.ok(app.indexOf('/frame-thickness-contract.css') > adapter);
  const active = load('public/user-shell.css');
  assert.match(active, /data-interface-app-mode="user"\]\[data-efhc-source-styles="true"\]/);
  // The generated file has legacy nested Admin selectors, but every such rule
  // must remain below the explicit USER-only root (and the link is USER-only).
  const selectors = [...active.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{/g)].map(m => m[1].trim());
  for (const selector of selectors.filter(s => s.includes('data-interface-app-mode="admin"'))) {
    assert.match(selector, /^\.efhc-independent-shell\[data-interface-app-mode="user"\]\[data-efhc-source-styles="true"\]/);
  }
  // Keep scope of the historical reference fragment checked, too.
  assert.doesNotMatch(css, /data-interface-app-mode="admin"/);
  assert.ok(css.includes('data-interface-app-mode="user"'));
});
test('frame geometry matches frozen source CSS and panel third stat spans both columns', () => {
  for(const marker of ['gap:.72rem','border-radius:1rem','padding:.85rem','font-size:1.3rem','font-size:.65rem','padding:.55rem','border-radius:.75rem','gap:.48rem','grid-column:1/-1']) {
    assert.ok(css.includes(marker), marker);
  }
});
test('theme ownership is retained: no CT selectors or global forced colors', () => {
  assert.doesNotMatch(css, /\[data-color-theme-id\s*=/);
  assert.doesNotMatch(css, /\[data-global-theme-id\s*=/);
  assert.doesNotMatch(css, /!important/);
  assert.match(css, /--efhc-route-border/);
});
