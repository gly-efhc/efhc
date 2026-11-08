import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { sourceRuntime } from "../helpers/source-runtime.mjs";

const source = (name) => readFileSync(new URL(`../../src/${name}`, import.meta.url), "utf8");
const h = sourceRuntime();
const {
  energyElapsedSinceSnapshotMs: elapsedSinceSnapshot,
  energyDisplayProjectionWindowMs: expiresAfter,
  projectEnergyD8: project,
  reconcileEnergyAnchor: reconcile,
} = h.load("lib/energyProjection.ts");

test("Fresh 30-second sync does not rewind the local BASE/VIP counter", () => {
  const serverA = "2026-11-08T12:00:00.000Z";
  const serverB = "2026-11-08T12:00:30.000Z";
  const clientNow = Date.parse(serverA) + 30_500;
  const initial = 100_000_000n;
  for (const perPanelRate of [692n, 741n]) {
    const aggregateRate = perPanelRate * 4n;
    const before = project(
      initial, aggregateRate,
      elapsedSinceSnapshot(serverA, Date.parse(serverA) + 100, clientNow),
    );
    const confirmedB = initial + aggregateRate * 30n;
    const after = project(
      confirmedB, aggregateRate,
      elapsedSinceSnapshot(serverB, Date.parse(serverB) + 100, clientNow),
    );
    assert.equal(before, after, "same timestamp must give the same D8 result at every refetch");
  }
});

test("Offline restart replays elapsed wall time from a persisted server snapshot", () => {
  const serverIso = "2026-11-08T00:00:00.000Z";
  const serverMs = Date.parse(serverIso);
  const fourHoursLater = serverMs + 4 * 3600 * 1000;
  const elapsed = elapsedSinceSnapshot(serverIso, serverMs + 150, fourHoursLater);
  assert.equal(elapsed, 4 * 3600 * 1000);
  const base = 5_000_000_000n;
  const rate = 741n * 5n;
  assert.equal(project(base, rate, elapsed), base + rate * BigInt(4 * 3600));
});

test("Offline projection stops at earliest server-confirmed panel expiry", () => {
  const serverIso = "2026-11-08T00:00:00.000Z";
  const expiryIso = "2026-11-08T00:30:00.000Z";
  const elapsed = elapsedSinceSnapshot(serverIso, Date.parse(serverIso), Date.parse(serverIso) + 4 * 3600 * 1000);
  const safeMs = Math.min(expiresAfter(serverIso, expiryIso), elapsed);
  assert.equal(safeMs, 30 * 60 * 1000);
  assert.equal(project(0n, 692n, safeMs), 692n * 1800n);
});

test("Known client clock skew cannot invent hours of energy from a fresh snapshot", () => {
  const serverIso = "2026-11-08T12:00:00.000Z";
  const clientReceivedAt = Date.parse(serverIso) + 60 * 60 * 1000;
  assert.equal(elapsedSinceSnapshot(serverIso, clientReceivedAt, clientReceivedAt), 0);
  assert.equal(elapsedSinceSnapshot(serverIso, clientReceivedAt, clientReceivedAt + 30_500), 30_500);
  assert.equal(elapsedSinceSnapshot(serverIso, clientReceivedAt, clientReceivedAt - 1), 0);
  assert.equal(elapsedSinceSnapshot("invalid", clientReceivedAt, clientReceivedAt + 60_000), 0);
});

test("Energy replay uses D8 integer math and allows genuine downward server corrections", () => {
  assert.equal(project(100_000_000n, 692n, 1500), 100_001_038n);
  assert.equal(project(100_000_000n, 741n, 1500), 100_001_111n);
  assert.equal(project(100n, 0n, 100_000), 100n);
  assert.equal(project(100n, 692n, -5), 100n);
  assert.equal(project(100n, 692n, Infinity), 100n);
  assert.equal(reconcile({base_scaled: 999n, base_client_ms: 0}, 400n, 250).base_scaled, 400n);
});

test("One projection path is used on hydration, each live tick and all refetches", () => {
  const energy = source("pages/index.tsx");
  const app = source("pages/_app.tsx");
  const snapshot = source("hooks/useSnapshot.ts");
  const snapshotSchema = source("services/snapshot.service.ts");
  assert.ok(energy.includes("s.meta.generation_checkpoint_at_iso ?? s.meta.server_now_iso"), "use committed energy boundary with legacy fallback");
  assert.ok(snapshotSchema.includes("generation_checkpoint_at_iso: z.string().nullable().optional()"), "optional wire compatibility");
  assert.match(energy, /energyElapsedSinceSnapshotMs\(/);
  assert.match(energy, /projectEnergyD8\(/);
  assert.match(energy, /snapshot_updated_at_ms=\{props\.snapshotUpdatedAt \?\? null\}/);
  assert.match(energy, /Math\.min\(projectUntilMs, elapsedMs\)/);
  assert.match(app, /updatedAt: snapshotUpdatedAt/);
  assert.match(app, /snapshotUpdatedAt=\{snapshotUpdatedAt\}/);
  assert.match(snapshot, /refetchInterval: globalId \? 30_000 : false/);
  assert.doesNotMatch(energy, /rate\s*=\s*0\.00000692/);
});

test("Cycle 0043: both available-kWh displays use one polled backend exchange preview", () => {
  const energy = source("pages/index.tsx");
  const app = source("pages/_app.tsx");
  const exchange = source("pages/exchange.tsx");
  const previewHook = source("queries/useExchange.ts");
  const snapshotHook = source("hooks/useSnapshot.ts");

  // Energy must remain SSR-renderable without a provider: the app shell owns
  // the backend request, and Energy only renders the confirmed prop.
  assert.doesNotMatch(energy, /useExchangePreview/);
  assert.match(energy, /available_kwh=\{props\.confirmedAvailableKwh \?\? null\}/);
  assert.match(app, /useExchangePreview\(router\.pathname === "\/"\)/);
  assert.match(app, /confirmedAvailableKwh=\{energyAvailablePreview\.data\?\.available_kwh \?\? null\}/);
  assert.match(energy, /props\.available_kwh === null[\s\S]*?formatFixedDown\(props\.available_kwh, 8\)/);
  assert.doesNotMatch(energy, /toScaled\(props\.available_kwh\)\s*\+\s*\(eLiveScaled\s*-\s*e0ScaledRaw\)/);

  assert.match(exchange, /const availableKwh = preview\?\.available_kwh \?\? null/);
  assert.doesNotMatch(exchange, /snapshotAvailable/);
  assert.match(exchange, /value=\{availableKwh === null \? "—" : format8\(availableKwh\)\}/);
  assert.match(previewHook, /queryKey: queryKeys\.exchange\.preview\(globalId\)/);
  assert.match(previewHook, /enabled: Boolean\(globalId\) && enabled/);
  assert.match(previewHook, /refetchInterval: globalId \? 30_000 : false/);
  assert.match(previewHook, /refetchOnWindowFocus: "always"/);
  assert.match(previewHook, /refetchOnReconnect: "always"/);
  assert.match(snapshotHook, /queryKey: queryKeys\.exchange\.preview\(globalId\),\s*refetchType: "active"/);
});
