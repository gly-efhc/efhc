import { ApiError, apiRequest } from "../api";
import { cmp8 } from "../format";
import { getClientAdProvider } from "./providers";
import type {
  AdRunPhase,
  AdRunResult,
  AdSessionState,
  NormalizedAdError,
  ProviderShowResult,
} from "./types";

const KNOWN_ERRORS = new Set<NormalizedAdError>([
  "NO_FILL",
  "NOT_CONFIGURED",
  "DISABLED",
  "NOT_SUPPORTED",
  "GEO_NOT_SUPPORTED",
  "LANG_NOT_SUPPORTED",
  "SDK_LOAD_FAILED",
  "TIMEOUT",
  "USER_SKIPPED",
  "PROVIDER_ERROR",
  "VERIFICATION_FAILED",
  "DAILY_LIMIT_REACHED",
  "SESSION_EXPIRED",
  "REWARD_NOT_ALLOWED",
]);

export class AdManagerClientError extends Error {
  code: NormalizedAdError;
  session?: AdSessionState;

  constructor(code: NormalizedAdError, session?: AdSessionState) {
    super(code);
    this.name = "AdManagerClientError";
    this.code = code;
    this.session = session;
  }
}

function normalizedError(error: unknown): NormalizedAdError {
  if (error instanceof AdManagerClientError) return error.code;
  let raw = "";
  if (error instanceof ApiError) {
    const payload = error.payload as { detail?: unknown } | undefined;
    raw = String(error.code || payload?.detail || "");
  } else if (error instanceof Error) {
    raw = error.message;
  }
  const code = raw.trim().toUpperCase() as NormalizedAdError;
  return KNOWN_ERRORS.has(code) ? code : "PROVIDER_ERROR";
}

function headers(appLanguage: string): Record<string, string> {
  return {
    "X-App-Language": String(appLanguage || "en"),
    "X-EFHC-Platform": "telegram-miniapp",
  };
}

async function createSession(
  taskCode: string,
  appLanguage: string,
): Promise<AdSessionState> {
  return await apiRequest<AdSessionState>("/ads/session", "POST", {
    headers: headers(appLanguage),
    body: { task_code: taskCode },
  });
}

async function fallbackSession(
  session: AdSessionState,
  appLanguage: string,
  reason: NormalizedAdError,
): Promise<AdSessionState> {
  return await apiRequest<AdSessionState>(
    `/ads/session/${encodeURIComponent(session.session_id)}/fallback`,
    "POST",
    { headers: headers(appLanguage), body: { reason } },
  );
}


async function clientTelemetry(
  session: AdSessionState,
  eventType: "ad_requested" | "preload_started" | "preload_success" | "preload_failed",
  metadata: Record<string, unknown> = {},
): Promise<void> {
  try {
    await apiRequest(
      `/ads/session/${encodeURIComponent(session.session_id)}/event`,
      "POST",
      { body: { event_type: eventType, metadata } },
    );
  } catch {
    // Telemetry не имеет права ломать показ или reward flow.
  }
}

async function markShown(session: AdSessionState): Promise<AdSessionState> {
  return await apiRequest<AdSessionState>(
    `/ads/session/${encodeURIComponent(session.session_id)}/shown`,
    "POST",
  );
}

async function clientComplete(
  session: AdSessionState,
  result: ProviderShowResult,
): Promise<AdSessionState> {
  return await apiRequest<AdSessionState>(
    `/ads/session/${encodeURIComponent(session.session_id)}/client-complete`,
    "POST",
    {
      body: {
        payload: {
          shown: result.shown !== false,
          completed: result.completed,
          ...(result.payload || {}),
        },
      },
    },
  );
}

async function getSession(session: AdSessionState): Promise<AdSessionState> {
  return await apiRequest<AdSessionState>(
    `/ads/session/${encodeURIComponent(session.session_id)}`,
    "GET",
  );
}

async function waitForServerVerification(
  initial: AdSessionState,
  onPhase?: (phase: AdRunPhase) => void,
): Promise<AdSessionState> {
  let current = initial;
  const deadline = Date.now() + 30_000;
  onPhase?.("verifying");
  while (Date.now() < deadline) {
    if (current.rewarded || ["failed", "fraud_rejected", "expired", "no_fill"].includes(current.status)) {
      return current;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    current = await getSession(current);
  }
  return current;
}

function noFill(session: AdSessionState): boolean {
  return session.status === "no_fill" || session.failure_code === "NO_FILL";
}

function noFallbackFor(error: NormalizedAdError): boolean {
  return [
    "DAILY_LIMIT_REACHED",
    "SESSION_EXPIRED",
    "VERIFICATION_FAILED",
    "USER_SKIPPED",
  ].includes(error);
}


async function withProviderTimeout<T>(promise: Promise<T>, seconds: unknown): Promise<T> {
  const timeoutMs = Math.max(1_000, Number(seconds || 8) * 1_000);
  let timer: number | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_resolve, reject) => {
        timer = window.setTimeout(() => reject(new Error("TIMEOUT")), timeoutMs);
      }),
    ]);
  } finally {
    if (timer !== undefined) window.clearTimeout(timer);
  }
}

export class AdManager {
  static async runRewardedAd(args: {
    taskCode: string;
    appLanguage: string;
    onPhase?: (phase: AdRunPhase) => void;
    requireZeroReward?: boolean;
  }): Promise<AdRunResult> {
    args.onPhase?.("loading");
    let session: AdSessionState;
    try {
      session = await createSession(args.taskCode, args.appLanguage);
    } catch (error) {
      const code = normalizedError(error);
      args.onPhase?.(code === "DAILY_LIMIT_REACHED" ? "daily_limit" : "failed");
      throw new AdManagerClientError(code);
    }

    if (args.requireZeroReward && cmp8(session.reward_efhcb, "0.00000000") !== 0) {
      args.onPhase?.("failed");
      throw new AdManagerClientError("REWARD_NOT_ALLOWED", session);
    }

    while (true) {
      if (noFill(session) || !session.provider?.code) {
        args.onPhase?.("no_fill");
        throw new AdManagerClientError("NO_FILL", session);
      }
      const adapter = getClientAdProvider(session.provider.code);
      const publicConfig = session.provider.public_config || {};
      let result: ProviderShowResult;
      if (publicConfig.preload === true) {
        await clientTelemetry(session, "preload_started");
      }
      try {
        args.onPhase?.("viewing");
        result = await withProviderTimeout(
          adapter.show(publicConfig),
          publicConfig.efhc_timeout_sec,
        );
        if (publicConfig.preload === true) {
          await clientTelemetry(session, "preload_success");
        }
      } catch (error) {
        const code = normalizedError(error);
        if (publicConfig.preload === true) {
          await clientTelemetry(session, "preload_failed", { reason: code });
        }
        if (noFallbackFor(code)) throw new AdManagerClientError(code, session);
        args.onPhase?.("loading");
        try {
          session = await fallbackSession(session, args.appLanguage, code);
          continue;
        } catch (fallbackError) {
          const fallbackCode = normalizedError(fallbackError);
          throw new AdManagerClientError(fallbackCode, session);
        }
      }

      if (result.noFill) {
        args.onPhase?.("loading");
        session = await fallbackSession(session, args.appLanguage, "NO_FILL");
        continue;
      }
      if (result.skipped || !result.completed) {
        throw new AdManagerClientError("USER_SKIPPED", session);
      }

      if (result.shown !== false) {
        session = await markShown(session);
      }
      args.onPhase?.("verifying");
      try {
        session = await clientComplete(session, result);
      } catch (error) {
        const code = normalizedError(error);
        throw new AdManagerClientError(code, session);
      }

      if (!session.rewarded && session.verification_level === "B") {
        session = await waitForServerVerification(session, args.onPhase);
      }
      if (session.rewarded) {
        args.onPhase?.("rewarded");
      } else if (session.status === "no_fill") {
        args.onPhase?.("no_fill");
      } else if (["failed", "fraud_rejected", "expired"].includes(session.status)) {
        args.onPhase?.("failed");
      }
      return { session, rewardEfhcb: session.reward_efhcb };
    }
  }
}

export function adManagerErrorCode(error: unknown): NormalizedAdError {
  return normalizedError(error);
}
