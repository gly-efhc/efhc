import { lstatSync, readlinkSync, symlinkSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
const link = fileURLToPath(new URL('../node_modules', import.meta.url));
const target = fileURLToPath(new URL('../../../frontend/node_modules', import.meta.url));
try {
  const stat = lstatSync(link);
  if (!stat.isSymbolicLink() || resolve(dirname(link), readlinkSync(link)) !== resolve(target)) {
    throw new Error('Frontend test dependencies must point to the single frontend installation');
  }
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
  symlinkSync(target, link, 'junction');
}
