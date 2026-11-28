import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(sourceDir, '../..');
const source = (p) => fs.readFileSync(path.join(root, p), 'utf8');

test('v908: Pages build allows SDK restoration and real user-initiated wallet transport', () => {
  const wallet=source('src/lib/wallet-provider/adapters/TonConnectAdapter.ts');
  const layout=source('src/components/Layout.tsx');
  assert.doesNotMatch(wallet,/if\s*\(process\.env\.NEXT_PUBLIC_EFHC_PAGES_PREVIEW/);
  assert.doesNotMatch(layout,/__EFHC_TONCONNECT_USER_ACTIVATED_UNTIL__/);
  assert.match(wallet,/bindVerifiedTonConnectWallet/);
  assert.match(wallet,/sendTonConnectTransaction\(requireUi\(\), tx, args\.wallet\)/);
  assert.match(layout,/if \(hasBoundWallet\)/);
  assert.match(layout,/wallet\.restore_requires_proof/);
  const app=source('src/pages/_app.tsx');
  const transport=source('src/lib/tonconnect.ts');
  assert.match(app,/NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1"/);
  assert.match(transport,/NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1"/);
  assert.match(transport,/requireGenesisTransactionNetwork\(\s*request\?\.network, connected\?\.account\?\.chain,/);
  assert.ok(transport.indexOf('requireGenesisTransactionNetwork(', transport.indexOf('export async function sendTonConnectTransaction')) < transport.indexOf('tonConnectUI.sendTransaction(', transport.indexOf('export async function sendTonConnectTransaction')));
  assert.match(transport,/TONCONNECT_TRANSACTION_RESPONSE_INVALID/);
});

test('Business operations use the explicit TEST adapter or production transport; no TEST fallback to production',()=>{
  const api=source('src/lib/api.ts');
  const dispatcher=source('src/data/transport.ts');
  const config=source('src/demo/config.ts');
  const transport=source('src/demo/transport.ts');
  assert.match(api,/return await transportRequest<T>\(path, method, opts\)/);
  assert.match(dispatcher,/if \(dataSource === "demo_backend"\) \{\s*const demo = await import\("\.\.\/demo"\);\s*demo\.register\(\);\s*\} else if \(dataSource === "production"\)/);
  assert.match(dispatcher,/throw new Error\("EFHC_UNKNOWN_DATA_SOURCE"\)/);
  assert.match(dispatcher,/initialization = null;\s*throw error;/);
  assert.match(dispatcher,/throw new Error\("EFHC_API_TRANSPORT_NOT_REGISTERED"\)/);
  assert.match(config,/url\.protocol !== "https:"/);
  assert.match(config,/url\.username \|\| url\.password/);
  assert.match(config,/EFHC_BACKEND_API_ORIGIN_INVALID/);
  assert.match(transport,/demoFetch\(`\$\{demoApiOrigin\(\)\}\$\{endpoint\}`/);
  assert.match(transport,/credentials: "include"/);
  assert.match(transport,/X-EFHC-Test-CSRF/);
  assert.match(transport,/if \(response\.status === 401\) invalidateDemoCredential/);
  assert.match(transport,/throw new ApiError/);
  assert.doesNotMatch(transport,/performProductionHttpRequest|productionTransport|demoUnifiedStore/);
});
