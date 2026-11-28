import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {localPagesBase} from '../parity/pages-base.mjs';

const root=fileURLToPath(new URL('../../../frontend/src/',import.meta.url));
const read=part=>fs.readFileSync(path.join(root,part),'utf8');

test('project basePath preserves one prefix and does not depend on deleted browser finance DEMO',()=>{
 const assets=read('lib/publicAssetPath.ts');
 assert.match(assets,/appBasePath/);
 assert.doesNotMatch(assets,/demoUnifiedStore|demoApiRequest|DEMO_GLOBAL_ID/);
 const pages=read('lib/appBasePath.ts');
 assert.match(pages,/withoutAppBasePath/);
 const shell=read('services/appShell.service.ts');
 assert.match(shell,/tonconnect-manifest\.json/);
});
test('browser verification changes project prefix without allowing external test destinations',()=>{
 for(const prefix of ['Test-3','efhc','future-name'])
  assert.equal(localPagesBase(`http://127.0.0.1:19243/${prefix}/`),`http://127.0.0.1:19243/${prefix}/`);
 for(const url of ['https://example.com/efhc/','http://127.0.0.1:19243/','http://127.0.0.1:19243/efhc/nested/','http://127.0.0.1:19243/efhc/?x=1'])
  assert.throws(()=>localPagesBase(url));
});
