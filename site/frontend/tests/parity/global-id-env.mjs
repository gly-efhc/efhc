// CI-only identity contract. A Global ID identifies the EFHC owner; it never grants Admin.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

export function isCanonicalGlobalId(value) {
  return typeof value === 'string' && /^[0-9]{10}$/.test(value) && value !== '0000000000';
}

export function verifyGlobalIdEnvironment(env = process.env) {
  const value = env.EFHC_TEST_GLOBAL_ID;
  assert.ok(isCanonicalGlobalId(value),
    'EFHC_TEST_GLOBAL_ID is missing or invalid: configure the canonical EFHC Global ID in GitHub Actions Secrets/Variables as EFHC_GLOBAL_ID or EFHC_TEST_GLOBAL_ID; never use a GitHub user ID');
  for (const key of ['NEXT_PUBLIC_EFHC_GLOBAL_ID', 'NEXT_PUBLIC_EFHC_TEST_GLOBAL_ID']) {
    assert.ok(!env[key], `Private Global ID must not be exposed through ${key}`);
  }
  return value;
}

// Run on the real CI environment and self-test the contract's unsafe edge cases.
// Do not print the identifier, bearer tokens, or configured variable contents.
if (process.argv[1] && fileURLToPath(import.meta.url) === fileURLToPath(new URL(`file://${process.argv[1]}`))) {
  for (const value of [undefined, null, '', '0000000000', '88', '000000088', '10000000000', '123456789x', ' 0000000088', '0000000088 ', 88]) {
    assert.equal(isCanonicalGlobalId(value), false, 'Invalid Global ID passed validation');
  }
  assert.equal(isCanonicalGlobalId('0000000088'), true, 'Leading zeros must survive canonical string handling');
  assert.equal(isCanonicalGlobalId('1234567890'), true);
  const expected = verifyGlobalIdEnvironment();

  const identityContract = fs.readFileSync(new URL('../../src/types/identity.ts', import.meta.url), 'utf8');
  const authContract = fs.readFileSync(new URL('../../src/lib/auth-session.ts', import.meta.url), 'utf8');
  const adminAccess = fs.readFileSync(new URL('../../src/pages/_app.tsx', import.meta.url), 'utf8');
  assert.match(identityContract, /GLOBAL_ID_PATTERN = \/\^\[0-9\]\{10\}\$\//);
  assert.match(identityContract, /GLOBAL_ID_ZERO = "0000000000"/);
  assert.match(authContract, /global_id: globalId/);
  assert.match(adminAccess, /fetchAdminAccess\(\)/);
  assert.match(adminAccess, /access\?\.global_id === globalId/);

  assert.equal(expected, '0000000088', 'CI Global ID must match the OWNER-approved SuperAdmin identity, without number coercion');
  console.log('EFHC_GLOBAL_ID_ENV_CONTRACT=PASS format=D10 canonical-string no-public-bundle server-authorization-required');
}
