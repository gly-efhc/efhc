import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
const read=(path)=>fs.readFileSync(new URL(path,sourceUrl),'utf8');
const hash=(path)=>crypto.createHash('sha256').update(fs.readFileSync(new URL(path,sourceUrl))).digest('hex');
test('v922 App restores v914 layout CSS entry and fixes TS compilation variables',()=>{
const src=read('../pages/_app.tsx');
assert.match(src,/const router = useRouter\(\);/);
assert.match(src,/const isBrowserShop = router\.pathname/);
assert.match(src,/import \"\.\.\/styles\/globals\.css\";/);
assert.doesNotMatch(src,/import \"\.\.\/styles\/user-shell-layout\.css\";/);
assert.doesNotMatch(src,/import \"\.\.\/styles\/bottom-navigation-dots\.css\";/);
});
test('v922 preserves visual baseline v914 globals/HUB/Layout and frozen stylesheet SHA',()=>{
const values={"src/styles/globals.css": "184fc7f9a9898c63e0fa3aaf1989553c9cc9354f9173ae9d06885ffc2e74da57", "src/features/hub/HubPage.tsx": "6cf03696e5cc8a94d0fab43c41ba7baad591a6bbff10fd4346fe049ae5302a2a", "src/components/Layout.tsx": "a9d691dbe49d3e4735de534e4e51920b36177424f89f7ae3a039d6d25a1a5fcc", "public/FRONTEND_v866.css": "4f08ead98e6b000817d5ea24965cd5d56d31db73d6bd53e56d9ca2c81350bfff", "public/SHOP_v866.css": "e95aaf7464ba6f7f014046fb1a311600d3b9a9a953879ff95443d80d4f450af6", "src/design-system/color-theme-registry.json": "90c6e2b60461a214cfad571a864eb800b1bc16135a26741e6f98f5151ad45949"};
for(const [p,sha] of Object.entries(values))assert.equal(hash('../../'+p),sha,`${p} modified`);
});
