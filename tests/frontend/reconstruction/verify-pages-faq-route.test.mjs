import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
const source = readFileSync(new URL('../../../deployment/pages-tools/fix_pages_assets.py', sourceUrl), 'utf8');
function rewrite(value) {
  const python = [
    "import sys, types",
    "source, value = sys.stdin.read().split('\\0', 1)",
    "module = types.ModuleType('pages_assets')",
    "exec(compile(source, 'fix_pages_assets.py', 'exec'), module.__dict__)",
    "sys.stdout.write(module.PATTERN.sub(lambda m: m.group(1) + '/Test-3/' + m.group(2), value))",
  ].join("\n");
  const result = spawnSync("python3", ["-c", python], {
    input: `${source}\0${value}`, encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}
test("Pages asset rewrite preserves the real FAQ route and Next client-side navigation", () => {
  for (const route of ['href="/faq"', 'router.push("/faq")', "'/faq'", 'href="/faq/"']) {
    assert.equal(rewrite(route), route, route);
  }
  assert.equal(rewrite('href="/Test-3/faq/"'), 'href="/Test-3/faq/"');
});
test("Pages rewrite still prefixes static translations and public image assets", () => {
  assert.equal(rewrite('fetch("/faq/ru.json")'), 'fetch("/Test-3/faq/ru.json")');
  assert.equal(rewrite('src="/assets/efhc/logo.svg"'), 'src="/Test-3/assets/efhc/logo.svg"');
});
