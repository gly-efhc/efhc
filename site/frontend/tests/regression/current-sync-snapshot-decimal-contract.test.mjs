import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { sourceRuntime } from "../helpers/source-runtime.mjs";

// Shape mirrors backend /sync/me?fresh=1, including Python Decimal's
// scientific zero. All values represent *read-only* test fixtures.
const backendFixture = {
  profile: {
    global_id: "0000000088", username: null, is_vip: false, has_activ: true,
    main_balance: "292.04647293", bonus_balance: "0E-8",
    available_kwh: "4.63450875", total_generated_kwh: "194.50098168",
    gen_per_sec_base: "0.00000692", gen_per_sec_vip: "0.00000741",
  },
  panels: {
    active_count: 13, total_generated_by_panels: "194.50098168",
    nearest_expire_at: "2027-03-30T10:00:00+00:00",
  },
  exchange_preview: {
    ok: true, available_kwh: "4.63450875", max_exchangeable_kwh: "4.63450875",
    rate_kwh_to_efhc: "1.00000000", detail: "",
  },
  meta: {
    server_now_iso: "2026-11-08T16:38:44Z",
    generation_checkpoint_at_iso: "2026-11-08T16:38:44Z",
    gen_per_sec_effective: "0.00008996",
    next_scheduler_eta_sec: 5, fallback_task_id: null,
  },
};

function snapshotModule(payload = backendFixture) {
  const h = sourceRuntime({overrides: {
    "../lib/api": {apiRequest: async () => payload},
  }});
  return h.load("services/snapshot.service.ts");
}

test("real sync contract accepts Python Decimal scientific zero and keeps nonzero Energy", async () => {
  const {fetchSyncSnapshot} = snapshotModule();
  const snap = await fetchSyncSnapshot();
  assert.equal(snap.profile.bonus_balance, "0.00000000");
  assert.equal(snap.profile.main_balance, "292.04647293");
  assert.equal(snap.profile.available_kwh, "4.63450875");
  assert.equal(snap.panels.active_count, 13);
  assert.equal(snap.meta.gen_per_sec_effective, "0.00008996");
  assert.equal(snap.meta.generation_checkpoint_at_iso, backendFixture.meta.generation_checkpoint_at_iso);
});

test("all snapshot D8 fields safely expand exact scientific notation without floating point", () => {
  const {syncSnapshotSchema} = snapshotModule();
  const fixture = structuredClone(backendFixture);
  fixture.profile.bonus_balance = "-0E-8";
  fixture.profile.available_kwh = "1E-8";
  fixture.profile.gen_per_sec_base = "6.92E-6";
  fixture.panels.total_generated_by_panels = "1.9450098168E+2";
  fixture.exchange_preview.rate_kwh_to_efhc = "1E+0";
  const snap = syncSnapshotSchema.parse(fixture);
  assert.equal(snap.profile.bonus_balance, "0.00000000");
  assert.equal(snap.profile.available_kwh, "0.00000001");
  assert.equal(snap.profile.gen_per_sec_base, "0.00000692");
  assert.equal(snap.panels.total_generated_by_panels, "194.50098168");
  assert.equal(snap.exchange_preview.rate_kwh_to_efhc, "1.00000000");
});

test("D8 rejects lossy 9th fractional digit, invalid exponent and invalid identity", () => {
  const {syncSnapshotSchema} = snapshotModule();
  for (const invalid of ["0.000000001", "9E-9", "1.000000009", "1E+999", "NaN", "Infinity"]) {
    const fixture = structuredClone(backendFixture);
    fixture.profile.bonus_balance = invalid;
    assert.equal(syncSnapshotSchema.safeParse(fixture).success, false, invalid);
  }
  const wrongOwner = structuredClone(backendFixture);
  wrongOwner.profile.global_id = "wrong";
  assert.equal(syncSnapshotSchema.safeParse(wrongOwner).success, false);
});

test("Energy renders 13 panels and verified generation, not a zero-owner placeholder", () => {
  const snap = snapshotModule().syncSnapshotSchema.parse(backendFixture);
  const h = sourceRuntime({overrides: {
    "../hooks/useT": {useT: () => (key) => key},
    "../hooks/useInterfaceVariantSurface": {
      useInterfaceVariantSurface: (group) => ({variant: group + "-01", handlers: {}, ref: null}),
    },
  }});
  const Page = h.load("pages/index.tsx").default;
  const html = renderToStaticMarkup(React.createElement(Page, {snap, snapshotMode:"live", snapshotStatus:"success"}));
  assert.match(html, /data-energy-mobile-proof="390px"/);
  assert.match(html, /194\.50098168/);
  assert.match(html, /data-energy-chip="active-panels"[\s\S]*?<strong>13<\/strong>/);
  assert.match(html, /data-energy-chip="generation-rate"[\s\S]*?0\.00008996/);
  assert.match(html, /data-energy-chip="available-kwh"[\s\S]*?4\.63450875/);
});

test("My Panels receives the same confirmed per-panel BASE rate from a valid snapshot", () => {
  const snap = snapshotModule().syncSnapshotSchema.parse(backendFixture);
  const h = sourceRuntime();
  const {confirmedPanelRateD8, projectPanelGeneratedD8} = h.load("lib/panelDisplayProjection.ts");
  const rate = confirmedPanelRateD8(snap.meta.gen_per_sec_effective, snap.panels.active_count);
  assert.equal(rate, "0.00000692");
  const panel = {generated_kwh:"23.02512050", base_gen_per_sec:rate, is_active:true, remaining_seconds:3600,
    expires_at:"2027-03-30T10:00:00+00:00"};
  const t0 = projectPanelGeneratedD8(panel, backendFixture.meta.server_now_iso, 0);
  const t1 = projectPanelGeneratedD8(panel, backendFixture.meta.server_now_iso, 1000);
  assert.equal(t0, "23.02512050");
  assert.equal(t1, "23.02512742");
});
