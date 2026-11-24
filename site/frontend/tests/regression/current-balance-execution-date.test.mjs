import assert from "node:assert/strict";
import fs from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";
import vm from "node:vm";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const page = read("../../src/components/profile/ProfileHistorySection.tsx");
const feed = read("../../src/components/profile/history/HistoryOperationFeed.tsx");
const resolve = (source, first, next, names) => {
  const from = source.indexOf("function " + first);
  const to = source.indexOf(next, from);
  assert.ok(from >= 0 && to > from);
  return vm.runInNewContext(stripTypeScriptTypes(source.slice(from, to)) + ";({" + names + "})");
};
const { executionDateForBalance } = resolve(page, "executionDateForBalance", "function presentHistoryOperation", "executionDateForBalance");
const { displayedTime, timeSortValue } = resolve(feed, "displayedTime", "function dateKey", "displayedTime,timeSortValue");

const created = "2026-11-24T12:00:00Z";
const paidAt = "2026-11-24T15:15:00Z";
test("withdrawals display only a server-confirmed execution timestamp", () => {
  const withdrawal = { source: "withdraw_request", occurred_at: created };
  for (const status of ["PENDING", "CANCELED", "REJECTED"])
    assert.equal(executionDateForBalance({ ...withdrawal, status, executed_at: paidAt }), null);
  assert.equal(executionDateForBalance({ ...withdrawal, status: "PAID" }), null);
  assert.equal(executionDateForBalance({ ...withdrawal, status: "PAID", executed_at: "bad" }), null);
  assert.equal(executionDateForBalance({ ...withdrawal, status: "PAID", executed_at: paidAt }), paidAt);
});
test("posted ledger timestamps survive older server responses, without invention", () => {
  assert.equal(executionDateForBalance({ source: "ledger", occurred_at: created }), created);
  assert.equal(executionDateForBalance({ source: "ledger", occurred_at: created, executed_at: null }), null);
  assert.equal(executionDateForBalance({ source: "other", occurred_at: created }), null);
});
test("an explicit null execution date never falls back or creates an ordering date", () => {
  assert.equal(displayedTime({ createdAt: created, executionAt: null }), null);
  assert.equal(timeSortValue({ createdAt: created, executionAt: null }), Number.NEGATIVE_INFINITY);
  assert.equal(displayedTime({ createdAt: created, executionAt: paidAt }), paidAt);
  assert.equal(displayedTime({ createdAt: created }), created);
  assert.match(feed, /time \? <time dateTime=\{time\}/);
});
