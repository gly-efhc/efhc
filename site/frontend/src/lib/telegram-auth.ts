import {
  acceptIssuedAuthSession,
} from "./auth-session-client";
import {
  requestTelegramSession,
  type TelegramSessionIssueResponse,
} from "../services/authSession.service";
import {
  clearReferralStartParam,
  clearReferralStartParamAfterFinalError,
  readReferralStartParamForLogin,
} from "./referral-start-param";

const TELEGRAM_INIT_DATA_MAX_LENGTH = 16_384;

function validateTransientInitData(value: unknown): string {
  if (typeof value !== "string" || !value || value !== value.trim()) {
    throw new Error("TELEGRAM_INIT_DATA_INVALID");
  }
  if (value.length > TELEGRAM_INIT_DATA_MAX_LENGTH) {
    throw new Error("TELEGRAM_INIT_DATA_TOO_LARGE");
  }
  return value;
}

export async function completeTelegramSessionLogin(
  initData: string,
): Promise<TelegramSessionIssueResponse> {
  const transientInitData = validateTransientInitData(initData);
  try {
    const referralStartParam = readReferralStartParamForLogin();
    const result = await requestTelegramSession(
      transientInitData,
      referralStartParam,
    );
    acceptIssuedAuthSession(result);
    clearReferralStartParam();
    return result;
  } catch (error) {
    clearReferralStartParamAfterFinalError(error);
    throw error;
  }
}
