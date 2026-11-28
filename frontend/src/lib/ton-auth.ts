import { apiRequest } from "./api";
import {
  type AuthSessionContext,
  type AuthSessionCredential,
} from "./auth-session";
import {
  acceptIssuedAuthSession,
  fetchAuthSessionContext,
  revokeAuthSession,
} from "./auth-session-client";
import {
  clearReferralStartParam,
  clearReferralStartParamAfterFinalError,
  readReferralStartParamForLogin,
} from "./referral-start-param";

export type TonProofLoginResponse = {
  verified: true;
  challenge_id: string;
  provider: "ton";
  ton_wallet_id: string;
  network: "mainnet" | "testnet";
  verified_at: string;
  global_id: string;
  account_outcome:
    | "existing_identity"
    | "existing_binding"
    | "registered";
  session: AuthSessionCredential;
};

function withReferralStartParam(
  proofRequest: unknown,
  referralStartParam: string | null,
): unknown {
  if (referralStartParam === null) return proofRequest;
  if (
    !proofRequest
    || typeof proofRequest !== "object"
    || Array.isArray(proofRequest)
  ) {
    throw new Error("TON_PROOF_REQUEST_INVALID");
  }
  return {
    ...(proofRequest as Record<string, unknown>),
    referral_start_param: referralStartParam,
  };
}

export async function completeTonProofLogin(
  proofRequest: unknown,
): Promise<TonProofLoginResponse> {
  try {
    const referralStartParam = readReferralStartParamForLogin();
    const body = withReferralStartParam(
      proofRequest,
      referralStartParam,
    );
    const result = await apiRequest<TonProofLoginResponse>(
      "/auth/ton/proof",
      "POST",
      { body },
    );
    acceptIssuedAuthSession(result);
    clearReferralStartParam();
    return result;
  } catch (error) {
    clearReferralStartParamAfterFinalError(error);
    throw error;
  }
}

export async function loadAuthSessionContext():
  Promise<AuthSessionContext> {
  return await fetchAuthSessionContext();
}

export async function logoutAuthSession(): Promise<void> {
  await revokeAuthSession();
}
