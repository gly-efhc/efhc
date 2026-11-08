import React, {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { EnergyVariantIcon } from
  "../components/icons/EnergyVariantIcon";
import { emptyOwnerSnapshot } from "../lib/browserFallback";
import { energyDisplayProjectionWindowMs, energyElapsedSinceSnapshotMs, projectEnergyD8 } from "../lib/energyProjection";
import { useT } from "../hooks/useT";
import { useExchangePreview } from "../queries/useExchange";
import type {
  SnapshotStatus,
  SyncSnapshot,
} from "../hooks/useSnapshot";
import { clamp, formatFixedDown } from "../lib/format";
import { USER_LEVEL_SKINS } from "../lib/skins";
import { useInterfaceVariantSurface } from
  "../hooks/useInterfaceVariantSurface";
import { EnergyUnitText } from "../components/energy/EnergyUnitText";

const SCALE = 8;
const LIVE_TICK_MS = 333;

function toScaled(v: string | number | null | undefined): bigint {
  const s0 = formatFixedDown(v, SCALE);
  const neg = s0.startsWith("-");
  const raw = neg ? s0.slice(1) : s0;
  const parts = raw.split(".");
  const intPart = parts[0] || "0";
  const frac = (parts[1] || "").padEnd(SCALE, "0");
  const digits = `${intPart}${frac}`.replace(/^0+(?=\d)/, "");
  const bi = BigInt(digits || "0");
  return neg ? -bi : bi;
}

function fromScaled(v: bigint): string {
  const neg = v < 0n;
  const raw = (neg ? -v : v).toString();
  const pad = raw.padStart(SCALE + 1, "0");
  const intPart = pad.slice(0, -SCALE);
  const frac = pad.slice(-SCALE);
  const out = `${intPart}.${frac}`;
  return neg ? `-${out}` : out;
}

function readStr(obj: any, path: string[], fallback: string): string {
  let cur: any = obj;
  for (const p of path) {
    if (cur && typeof cur === "object" && p in cur) cur = cur[p];
    else return fallback;
  }
  if (cur === null || cur === undefined) return fallback;
  return String(cur);
}

function readIntStr(
  obj: any,
  path: string[],
  fallback: string,
): string {
  let cur: any = obj;
  for (const p of path) {
    if (cur && typeof cur === "object" && p in cur) cur = cur[p];
    else return fallback;
  }
  if (cur === null || cur === undefined) return fallback;
  const s = String(cur).trim();
  if (!s) return fallback;
  return /^\d+$/.test(s) ? s : fallback;
}

type LiveBlockProps = {
  confirmed: boolean;
  server_now_iso: string | null;
  nearest_expire_at: string | null;
  snapshot_updated_at_ms: number | null;
  lifetime_kwh: string;
  gen_per_sec_effective: string;
  active_panels: string;
  available_kwh: string | null;
  thresholds_scaled: bigint[];
  hide_balances: boolean;
  labels: {
    energy: string;
    total_generated: string;
    progress: string;
    kwh_suffix: string;
    gen_rate: string;
    panels_owned: string;
    available_kwh_chip: string;
  };
};

function LiveEnergyBlock(props: LiveBlockProps) {
  const energyFrameSurface = useInterfaceVariantSurface<HTMLElement>("EG", {
    registerDots: false,
  });
  const iconSurface = useInterfaceVariantSurface<HTMLDivElement>("EI", { registerDots: false });
  const progressSurface = useInterfaceVariantSurface<HTMLDivElement>("PB", {
    dotsPlacement: "below",
  });
  const e0ScaledRaw = useMemo(
    () => toScaled(props.lifetime_kwh),
    [props.lifetime_kwh],
  );
  const vScaledRaw = useMemo(
    () => toScaled(props.gen_per_sec_effective),
    [props.gen_per_sec_effective],
  );
  const vScaled = vScaledRaw < 0n ? 0n : vScaledRaw;
  // A cached server snapshot may include an expiry that reduces active panels.
  // Until the backend confirms the new active count, stop local display
  // extrapolation at the first known expiry rather than inventing more energy.
  const projectUntilMs = useMemo(
    () => energyDisplayProjectionWindowMs(props.server_now_iso, props.nearest_expire_at),
    [props.server_now_iso, props.nearest_expire_at],
  );

  // Monotonic live clock with a wall-time origin. Cached snapshots can span
  // complete page restarts; the authoritative server timestamp anchors both
  // restored and fresh projections without resetting the counter at refetch.
  const clockRef = useRef({
    wall_ms: Date.now(),
    monotonic_ms: performance.now(),
  });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setTick((x) => x + 1);
  }, [e0ScaledRaw, props.server_now_iso, props.snapshot_updated_at_ms, vScaled]);

  useEffect(() => {
    if (!props.server_now_iso || vScaled === 0n) return;
    const id = window.setInterval(() => {
      setTick((x) => x + 1);
    }, LIVE_TICK_MS);
    return () => window.clearInterval(id);
  }, [props.server_now_iso, vScaled]);

  const localEnergyScaled = useMemo(() => {
    const confirmedScaled = e0ScaledRaw < 0n ? 0n : e0ScaledRaw;
    // Keep the statically exported first paint identical during hydration.
    // The mounted tick replays the time elapsed since the cached server stamp.
    if (tick === 0 || !props.server_now_iso) return confirmedScaled;
    const monotonicWallMs = clockRef.current.wall_ms
      + Math.max(0, performance.now() - clockRef.current.monotonic_ms);
    const clientNowMs = Math.max(Date.now(), monotonicWallMs);
    const elapsedMs = energyElapsedSinceSnapshotMs(
      props.server_now_iso,
      props.snapshot_updated_at_ms,
      clientNowMs,
    );
    // A missing full panel-expiry timeline must not invent post-expiry energy.
    const safeMs = Math.min(projectUntilMs, elapsedMs);
    return projectEnergyD8(confirmedScaled, vScaled, safeMs);
  }, [e0ScaledRaw, props.server_now_iso, props.snapshot_updated_at_ms, projectUntilMs, tick, vScaled]);

  const eLiveScaled = localEnergyScaled;

  const level = useMemo(() => {
    let current = 1;
    for (let index = 1; index < props.thresholds_scaled.length; index += 1) {
      const threshold = props.thresholds_scaled[index];
      if (threshold !== undefined && eLiveScaled >= threshold) {
        current = index + 1;
      }
    }
    return current;
  }, [eLiveScaled, props.thresholds_scaled]);

  const levelName = USER_LEVEL_SKINS[level - 1]?.name || "Eco Initiate";

  const startScaled = useMemo(() => {
    return props.thresholds_scaled[level - 1] ?? 0n;
  }, [level, props.thresholds_scaled]);

  const endScaled = useMemo(() => {
    if (level >= 12) return null;
    return props.thresholds_scaled[level] ?? null;
  }, [level, props.thresholds_scaled]);

  const progressPct = useMemo(() => {
    if (level >= 12) return 100;
    if (!endScaled) return 50;
    const span = endScaled - startScaled;
    if (span <= 0n) return 50;

    let num = eLiveScaled - startScaled;
    if (num < 0n) num = 0n;
    if (num > span) num = span;

    const pct = (num * 100n) / span;
    const v = parseInt(pct.toString(), 10);
    const basePct = !Number.isFinite(v) ? 0 : v < 0 ? 0 : v > 100 ? 100 : v;
    // FRONTEND_v127 owner decision: the user-level progress presentation is
    // advanced by +50 percentage points, capped at 100. Level thresholds,
    // generated kWh and backend economy semantics remain unchanged.
    return Math.min(100, basePct + 50);
  }, [eLiveScaled, endScaled, level, startScaled]);

  const prefersReducedMotion = useMemo(() => {
    if (typeof window === "undefined") return true;
    const q = "(prefers-reduced-motion: reduce)";
    return window.matchMedia(q).matches;
  }, []);

  const [displayPct, setDisplayPct] = useState(0);
  const progressFirstPaint = useRef(false);

  useEffect(() => {
    if (prefersReducedMotion) {
      progressFirstPaint.current = true;
      setDisplayPct(progressPct);
      return;
    }
    if (!progressFirstPaint.current) {
      progressFirstPaint.current = true;
      const id = window.requestAnimationFrame(() => setDisplayPct(progressPct));
      return () => window.cancelAnimationFrame(id);
    }
    // Keep the last painted percentage during each new D8 tick; CSS transitions
    // smoothly to the updated value instead of visibly resetting to zero.
    setDisplayPct(progressPct);
  }, [prefersReducedMotion, progressPct]);

  const fillClassName = prefersReducedMotion
    ? "efhc-energy-progress-fill efhc-no-motion"
    : "efhc-energy-progress-fill";

  const progressInLevel = useMemo(() => {
    if (level >= 12) return "MAX";
    if (!endScaled) return "0.00000000";
    const span = endScaled - startScaled;
    const raw = eLiveScaled - startScaled;
    const v = raw < 0n ? 0n : raw > span ? span : raw;
    return fromScaled(v);
  }, [eLiveScaled, endScaled, level, startScaled]);

  const remainingKwh = useMemo(() => {
    if (level >= 12) return "MAX";
    if (!endScaled) return "0.00000000";
    const raw = endScaled - eLiveScaled;
    const v = raw < 0n ? 0n : raw;
    return fromScaled(v);
  }, [eLiveScaled, endScaled, level]);

  const heroText = useMemo(
    () => fromScaled(eLiveScaled),
    [eLiveScaled],
  );


  const visibleProgressPct = displayPct;
  const shownProgress = props.hide_balances
    ? "••••••••"
    : progressInLevel;
  const shownRemaining = props.hide_balances
    ? "••••••••"
    : remainingKwh;
  const shownRate = props.hide_balances
    ? "••••••••"
    : formatFixedDown(props.gen_per_sec_effective, 8);
  // Only the backend exchange preview confirms kWh available to exchange.
  // The local ticker above remains exclusive to lifetime energy and progress.
  const shownAvailable = props.hide_balances
    ? "••••••••"
    : props.available_kwh === null
      ? "—"
      : formatFixedDown(props.available_kwh, 8);

  return (
    <section
      ref={energyFrameSurface.ref}
      {...energyFrameSurface.handlers}
      className="efhc-energy-stage"
      data-energy-mobile-stage="true"
      data-eg={energyFrameSurface.variant}
      data-energy-frame-theme-zone="stage-minus-local-zones"
      data-global-header-boundary="excluded"
      data-canon-energy="true"
    >
      <div className="efhc-energy-stage_image" />
      <div className="efhc-energy-stage_veil" />
      <div className="efhc-energy-stage_body">
        <div className="efhc-energy-stage_eyebrow">
          {props.labels.energy}
        </div>

        <div className="efhc-energy-stage_meter">
          <div className="efhc-energy-stage_icon-slot">
            <div
              ref={iconSurface.ref}
              className="efhc-energy-stage_icon-hit-zone"
              data-energy-icon-hit-zone="1cm"
            >
              <div
                className="efhc-energy-stage_coin"
                data-ei={iconSurface.variant}
              >
                <EnergyVariantIcon variant={iconSurface.variant} size={28} />
              </div>
            </div>
          </div>
          <div
            className="efhc-energy-stage_value"
            data-energy-value-safe="true"
            data-canon-energy-type="css-source-v866"
          >
            {props.hide_balances
              ? "••••••••"
              : heroText}
          </div>
        </div>

        <div className="efhc-energy-stage_subtitle">
          <EnergyUnitText text={props.labels.total_generated} />
        </div>

        <div className="efhc-energy-stage_progress-head">
          <span>{props.labels.progress}</span>
          <span>{displayPct}%</span>
        </div>

        <div
          ref={progressSurface.ref}
          {...progressSurface.handlers}
          className="efhc-energy-stage_progress-zone"
          data-energy-progress-selection-zone="progress-top-to-stage-bottom"
          data-pb={progressSurface.variant}
        >
          <div
            className="efhc-energy-progress-track"
            data-pb={progressSurface.variant}
            data-level-progress-boost-pp="50"
            data-level-progress-centered="true"
            data-progress-canon="true"
          >
            <div
              className={fillClassName}
              data-has-progress={visibleProgressPct > 0 ? "true" : "false"}
              style={{ width: `${visibleProgressPct}%` }}
            />
          </div>

          <div className="efhc-energy-stage_level" data-energy-level-name={levelName}>
            <strong><span data-i18n-fixed-token="Lvl">Lvl</span> {level}</strong>
            <span aria-hidden="true">·</span>
            <b>{levelName}</b>
          </div>

          <div
            className="efhc-energy-stage_range"
            data-energy-range-safe="true"
          >
            <span>{formatFixedDown(fromScaled(startScaled), 2)}</span>
            <span
              className="efhc-energy-stage_range-center"
              data-energy-range-center="remaining-to-next-level"
              aria-label={level >= 12 ? "MAX" : `До следующего уровня: ${shownRemaining} ${props.labels.kwh_suffix}`}
            >
              {shownRemaining}
              {remainingKwh === "MAX" ? "" : <EnergyUnitText text={props.labels.kwh_suffix} />}
            </span>
            <span>
              {endScaled
                ? formatFixedDown(fromScaled(endScaled), 2)
                : shownRemaining}
            </span>
          </div>

          <div
            className="efhc-energy-stage_chips"
            data-energy-chip-count="3"
          >
          <div
            className="efhc-energy-chip"
            data-energy-chip="active-panels"
          >
            <span>{props.labels.panels_owned}</span>
            <strong>{props.active_panels}</strong>
          </div>
          <div
            className="efhc-energy-chip"
            data-energy-chip="generation-rate"
          >
            <span>
              {props.labels.gen_rate} <EnergyUnitText text="kWh/s" />
            </span>
            <strong className="tabular-nums">
              {shownRate}
            </strong>
          </div>
          <div
            className="efhc-energy-chip"
            data-energy-chip="available-kwh"
          >
            <span><EnergyUnitText text={props.labels.available_kwh_chip} /></span>
            <strong className="tabular-nums">
              {shownAvailable}
            </strong>
          </div>
        </div>

        </div>
      </div>
    </section>
  );
}

const LiveEnergyHeroAndProgress = memo(LiveEnergyBlock);

export default function EnergyPage(props: {
  snap: SyncSnapshot | null;
  snapshotStatus?: SnapshotStatus;
  snapshotMode?: "live" | "browser-preview";
  snapshotRefreshing?: boolean;
  snapshotUpdatedAt?: number;
  refreshSnapshot?: () => void;
}) {
  const t = useT();
  const previewQuery = useExchangePreview();
  const s = props.snap ?? emptyOwnerSnapshot();

  const thresholdsKwh = useMemo(
    () => USER_LEVEL_SKINS.map((item) => String(item.min_kwh)),
    [],
  );

  const thresholdsScaled = useMemo(() => {
    return thresholdsKwh.map((x) => toScaled(`${x}.00000000`));
  }, [thresholdsKwh]);

  const activePanels = readIntStr(s, ["panels", "active_count"], "0");

  return (
    <div
      className="efhc-energy-page"
      data-energy-mobile-proof="390px"
      data-energy-state="content"
    >
      <LiveEnergyHeroAndProgress
        key={s.profile.global_id}
        confirmed={Boolean(s.meta.server_now_iso)}
        server_now_iso={s.meta.generation_checkpoint_at_iso ?? s.meta.server_now_iso}
        nearest_expire_at={s.panels.nearest_expire_at ?? null}
        snapshot_updated_at_ms={props.snapshotUpdatedAt ?? null}
        lifetime_kwh={readStr(
          s,
          ["profile", "lifetime_generated_kwh"],
          s.profile.total_generated_kwh,
        )}
        gen_per_sec_effective={s.meta.gen_per_sec_effective}
        active_panels={activePanels}
        available_kwh={previewQuery.data?.available_kwh ?? null}
        thresholds_scaled={thresholdsScaled}
        hide_balances={false}
        labels={{
          energy: t("energy.title"),
          total_generated: t("energy.total_generated_hero"),
          progress: t("energy.progress_label"),
          kwh_suffix: t("energy.kwh_suffix_spaced"),
          gen_rate: t("energy.gen_rate_card"),
          panels_owned: t("energy.panels_owned"),
          available_kwh_chip: t("energy.available_kwh_chip"),
        }}
      />
    </div>
  );
}
