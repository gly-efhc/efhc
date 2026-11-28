export type NormalizedAdError =
  | "NO_FILL"
  | "NOT_CONFIGURED"
  | "DISABLED"
  | "NOT_SUPPORTED"
  | "GEO_NOT_SUPPORTED"
  | "LANG_NOT_SUPPORTED"
  | "SDK_LOAD_FAILED"
  | "TIMEOUT"
  | "USER_SKIPPED"
  | "PROVIDER_ERROR"
  | "VERIFICATION_FAILED"
  | "DAILY_LIMIT_REACHED"
  | "SESSION_EXPIRED"
  | "REWARD_NOT_ALLOWED";

export type AdSessionState = {
  session_id: string;
  task_code: string;
  status: string;
  primary_provider: string | null;
  actual_provider: string | null;
  provider: {
    code: string;
    public_config: Record<string, unknown>;
  } | null;
  reward_efhcb: string;
  expires_at: string;
  failure_code: string | null;
  fallback_count: number;
  verification_level: string | null;
  estimated_revenue_usd: string | null;
  actual_revenue_usd: string | null;
  rewarded: boolean;
  test_mode: boolean;
};

export type ProviderShowResult = {
  completed: boolean;
  shown?: boolean;
  noFill?: boolean;
  skipped?: boolean;
  payload?: Record<string, unknown>;
};

export type AdProviderClientAdapter = {
  code: string;
  show(publicConfig: Record<string, unknown>): Promise<ProviderShowResult>;
};

export type AdRunPhase =
  | "loading"
  | "viewing"
  | "verifying"
  | "rewarded"
  | "no_fill"
  | "daily_limit"
  | "failed";

export type AdRunResult = {
  session: AdSessionState;
  rewardEfhcb: string;
};
