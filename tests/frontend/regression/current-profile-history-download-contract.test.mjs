import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL("../../../frontend/" + path, import.meta.url), "utf8");

test("CSV and XLSX use authenticated, scoped HTTPS download requests", () => {
  const service = read("src/services/profile.service.ts").split("export async function downloadProfileHistoryExport(")[1];
  assert.ok(service);
  assert.match(service, /export-ticket\?\$\{query\.toString\(\)\}`, "POST"/);
  assert.match(service, /getAuthSessionRevision\(\) !== revision/);
  assert.match(service, /new URL\("export-download", response\.url\)/);
  assert.match(service, /url\.searchParams\.set\("ticket", grant\.ticket\)/);
  assert.match(service, /webApp\.downloadFile\(\{ url: url\.href, file_name: grant\.filename \}/);
  assert.match(service, /anchor\.href = url\.href/);
  assert.doesNotMatch(service, /URL\.createObjectURL\(blob\)/);
});

test("History and withdrawal export never report unverified local file persistence", () => {
  assert.doesNotMatch(read("src/features/profile/WebProfilePage.tsx"), /toast\(t\("history\.export_success"\)/);
  assert.doesNotMatch(read("src/pages/withdraw.tsx"), /toast\(t\("withdraw\.export_success"\)/);
});

test("One download coordinator uses no application confirmation and settles native outcomes", () => {
  const service = read("src/services/profile.service.ts").split("export async function downloadProfileHistoryExport(")[1];
  assert.match(service, /if \(profileDownloadInFlight\) return "busy"/);
  assert.match(service, /finally \{\s*profileDownloadInFlight = false/);
  assert.match(service, /accepted === true \? "requested" : accepted === false \? "cancelled" : "unknown"/);
  assert.match(service, /setTimeout\(\(\) => settle\("unknown"\), 120_000\)/);
  assert.match(service, /return await new Promise<ProfileDownloadOutcome>/);
  assert.doesNotMatch(service, /telegramConfirm|showConfirm|showPopup|window\.confirm|ConfirmationDialog/);
});
