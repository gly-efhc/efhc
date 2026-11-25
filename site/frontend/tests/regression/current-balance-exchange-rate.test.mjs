import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../../src/components/profile/ProfileHistorySection.tsx", import.meta.url), "utf8");
const formatter = source.slice(source.indexOf("function categoryForItem("), source.indexOf("export function ProfileHistorySection("));
const { categoryForItem, presentHistoryOperation } = runInNewContext(
  stripTypeScriptTypes(formatter, { mode: "strip" }) + "\n({ categoryForItem, presentHistoryOperation })",
  {
    balanceTypeLabel: (value) => value,
    historyOperationKindLabel: (value) => value,
    historySourceLabel: (value) => value,
    historyStatusLabel: (value) => value,
  },
);
const base = {
  id: "9006", source: "ledger", kind: "balance_transfer", direction: "credit",
  occurred_at: "2026-11-25T00:00:00Z", executed_at: "2026-11-25T00:00:00Z",
  balance_type: "main", status: null, asset: "EFHCm",
  amount_efhc: "25", amount_asset: null, reason: "exchange_kwh",
};
const cardFor = (item) => presentHistoryOperation(item, "ru", (key) => key, (reason) => reason);

for (const [name, item] of [
  ["historical ledger operation", base],
  ["current exchange operation", { ...base, kind: "exchange", reason: "exchange_kwh_to_efhc" }],
]) {
  test(`Balance shows one fixed rate in details of a ${name}`, () => {
    assert.equal(categoryForItem(item), "exchange");
    const card = cardFor(item);
    const rates = card.details.filter(({ label }) => label === "history.detail_rate");
    assert.equal(rates.length, 1);
    assert.equal(rates[0].value, "1 kWh = 1 EFHCm");
    assert.doesNotMatch(card.subtitle, /1 kWh = 1 EFHCm/);
  });
}

test("a panel purchase keeps its PNL and does not gain an exchange rate", () => {
  const card = cardFor({ ...base, reason: "panel_activation", direction: "debit", panel_public_id: "PNL-00005557" });
  assert.equal(card.details.some(({ label }) => label === "history.detail_rate"), false);
  assert.equal(card.details.find(({ label }) => label === "panels.panel_id")?.value, "PNL00005557");
});
