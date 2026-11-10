import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { sourceRuntime } from "../helpers/source-runtime.mjs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SRC = fileURLToPath(new URL("../../src/", import.meta.url));
const source = name => readFileSync(path.join(SRC, name), "utf8");
const owner = "0000000088";
const basePanel = {
  public_id: "PNL-00000001",
  generated_kwh: "12.00000000",
  base_gen_per_sec: "0.00001000",
  is_active: true,
  remaining_seconds: 10,
  expires_at: "2026-11-07T12:00:10Z",
};
const now = "2026-11-07T12:00:00Z";

test("The existing PNL card uses a shared local tick, confirmed list and exact D8 projection", () => {
  const h = sourceRuntime();
  const { projectPanelGeneratedD8: projected, confirmedPanelRateD8: confirmedRate } = h.load("lib/panelDisplayProjection.ts");
  assert.equal(confirmedRate("0.00001482",2), "0.00000741", "VIP active per-panel rate");
  assert.equal(confirmedRate("0.00001384",2), "0.00000692", "Base active per-panel rate");
  assert.equal(confirmedRate("0.00001483",2), null, "non-divisible aggregate must not invent a rate");
  assert.equal(confirmedRate("0.00001482",0), null);
  assert.equal(projected(basePanel, now, 0), "12.00000000");
  assert.equal(projected(basePanel, now, 333), "12.00000333");
  assert.equal(projected(basePanel, now, 1500), "12.00001500");
  assert.equal(projected(basePanel, now, 10000), "12.00010000");
  assert.equal(projected(basePanel, now, 20000), "12.00010000", "never grow past known panel expiry");
  assert.equal(projected({ ...basePanel, is_active: false }, now, 20000), "12.00000000");
  assert.equal(projected({ ...basePanel, remaining_seconds: 1 }, now, 20000), "12.00001000");
  assert.equal(projected({ ...basePanel, base_gen_per_sec: "0.00000000" }, now, 9000), "12.00000000");
  assert.equal(projected(basePanel, null, 9000), "12.00000000");
  assert.equal(projected(basePanel, now, Number.POSITIVE_INFINITY), "12.00000000");
  const src = source("pages/panels/portfolio.tsx");
  assert.match(src, /projectPanelGeneratedD8\(/);
  assert.match(src, /confirmedPerPanelRateD8/);
  assert.ok(src.includes("!props.snap.profile.is_vip"), "VIP rate guard must remain in PNL card");
  assert.match(src, /setInterval\(updateNow, 333\)/);
  assert.match(src, /data-panel-countdown-live="client-stopwatch"/);
  assert.match(src, /data-panel-identity=\{p\.public_id \?\? undefined\}/);
  assert.doesNotMatch(src, /setInterval\(updateNow, 1_000\)/);
});

test("PNL list and tab/owner-specific cards survive offline reload without retaining a second owner", () => {
  const disk = new Map();
  const runtime = sourceRuntime({storage:disk});
  const query = runtime.load("lib/queryClient.ts");
  const c = query.createEfhcQueryClient();
  query.activateUserDataOwner(c, owner, false);
  const key = ["panels", owner, "list", "active", "oldest"];
  const data = { pages:[{server_now_utc: now, items:[{...basePanel,id:1}], next_cursor:null}], pageParams:[null] };
  c.setQueryData(key, data);
  assert.equal(JSON.stringify(c.getQueryData(key)),JSON.stringify(data));
  const reload = sourceRuntime({storage:disk});
  const q2 = reload.load("lib/queryClient.ts");
  const restored = q2.createEfhcQueryClient();
  q2.activateUserDataOwner(restored, owner, false);
  assert.equal(JSON.stringify(restored.getQueryData(key)), JSON.stringify(data));
  q2.activateUserDataOwner(restored, "0000000077", false);
  assert.equal(restored.getQueryData(key), undefined);
  assert.equal([...disk.values()].join("").includes("ACCESS_TOKEN_SECRET"), false);
  c.clear();restored.clear();
});

test("Energy, indicator colors, PNL countdown and progress bars keep their accepted geometry and non-resetting values", () => {
  const energy = source("pages/index.tsx");
  assert.match(energy, /LIVE_TICK_MS = 333/);
  assert.match(energy, /performance\.now\(\)/);
  assert.match(energy, /progressFirstPaint/);
  assert.match(energy, /setDisplayPct\(progressPct\)/);
  assert.doesNotMatch(energy, /setDisplayPct\(0\)/);
  assert.match(energy, /Math\.min\(projectUntilMs/);
  const h = sourceRuntime();
  const progress = h.load("components/dashboard/ProgressSystem.tsx");
  for(const value of [-1, 0, 25, 50, 100, 130, Infinity, NaN]){
    const normalized = progress.normalizeDashboardProgress(value);
    assert.ok(normalized.percent >= 0 && normalized.percent <= 100);
    if(Number.isFinite(value)) assert.equal(normalized.percent,Math.max(0,Math.min(value,100)));
    else assert.equal(normalized.percent,0);
  }
  const styles = source("styles/global-theme-energy-progress-contract.css");
  assert.ok(styles.includes("efhc-energy-progress"));
  const indicators = source("components/interface-settings/InterfaceIndicators.tsx");
  assert.ok(indicators.includes("data-indicator-group"));
  const referrals = source("pages/referrals.tsx");
  assert.ok(referrals.includes("Number.isFinite(raw)"), "malformed fraction must not produce NaN");
  assert.ok(referrals.includes("Number.isFinite(rawLevel)"), "malformed level must not produce NaN");
  assert.ok(referrals.includes("style={{ width: progressPct }}"), "referral progress must bind sanitized percent");
});

test("Local user settings survive reload without Telegram, remain owner-scoped, and sync after local choice", async () => {
  const disk=new Map();
  const runtime=sourceRuntime({storage:disk});
  const query=runtime.load("lib/queryClient.ts");
  const client=query.createEfhcQueryClient();
  query.activateUserDataOwner(client,owner,false);
  const settings=runtime.load("lib/settings.ts");
  const selection={...settings.resetSettings(),lang:"ru",color_theme_id:"CT-03",music_enabled:true,sfx_enabled:false,reduce_motion:true};
  settings.saveSettings(selection);
  const other=sourceRuntime({storage:disk});
  const reloadQuery=other.load("lib/queryClient.ts");
  const client2=reloadQuery.createEfhcQueryClient();
  reloadQuery.activateUserDataOwner(client2,owner,false);
  const stored=other.load("lib/settings.ts").loadSettings();
  for(const field of ["lang","color_theme_id","music_enabled","sfx_enabled","reduce_motion"])assert.equal(stored[field],selection[field]);
  reloadQuery.activateUserDataOwner(client2,"0000000044",false);
  const otherSettings=other.load("lib/settings.ts").loadSettings();
  assert.equal(otherSettings.color_theme_id,"CT-01");
  // OWNER: a newly bound Global ID receives the current default (ON), not a previous owner's setting.
  assert.equal(otherSettings.music_enabled,true);
  client.clear();client2.clear();
});
