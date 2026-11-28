import { apiRequest } from "../lib/api";
import type { AuthSessionCredential } from "../lib/auth-session";

export type TelegramSessionIssueResponse = {
  provider: "telegram";
  global_id: string;
  account_outcome:
    | "existing_identity"
    | "existing_legacy_account"
    | "registered";
  session: AuthSessionCredential;
};

export async function requestAuthSessionContext(): Promise<unknown> {
  return await apiRequest<unknown>("/auth/session", "GET");
}

export async function requestAuthLogout(): Promise<void> {
  await apiRequest<void>("/auth/logout", "POST");
}

export async function requestTelegramSession(
  initData: string,
  referralStartParam: string | null = null,
): Promise<TelegramSessionIssueResponse> {
  return await apiRequest<TelegramSessionIssueResponse>(
    "/auth/telegram/session",
    "POST",
    {
      headers: {
        "X-Telegram-Init-Data": initData,
      },
      body: referralStartParam === null
        ? undefined
        : { referral_start_param: referralStartParam },
    },
  );
}
