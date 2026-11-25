import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("../../src/pages/panels/portfolio.tsx", import.meta.url), "utf8");

test("My Panels omits end-of-list text but keeps incremental loading and its pagination gate", () => {
  assert.doesNotMatch(page, /common\.end/);
  assert.match(page, /loading && items\.length > 0 \? \([\s\S]*?t\("common\.loading"\)/);
  assert.match(page, /shouldRequestNextPanelPage\(\{/);
  assert.match(page, /listQuery\.fetchNextPage\(\)/);
});
