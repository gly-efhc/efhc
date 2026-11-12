/** Safe user-visible failure codes without leaking TON addresses or provider URLs. */
export type DirectDepositFailureStage = "metadata" | "jetton_wallet" | "wallet_send" | "wallet_connection";

export function describeDirectDepositFailure(
  cause: unknown,
  stage: DirectDepositFailureStage,
): string {
  const record = (
    cause && typeof cause === "object"
      ? cause as { code?: unknown; message?: unknown }
      : {}
  );
  const message = typeof record.message === "string" ? record.message : "";
  const code = typeof record.code === "string" ? record.code : "";

  const safeKnownReason = [message, code].find((value) =>
    /^(?:TON_|JETTON_|EFHC_|INVALID_|SENDER_|RECEIVER_|FORWARD_|WALLET_)[A-Z0-9_]{3,96}$/.test(value)
  );
  if (safeKnownReason) return `${stage}:${safeKnownReason}`;

  const combined = `${message} ${code}`;
  if (/\b429\b|rate.limit|too many requests/i.test(combined)) {
    return `${stage}:TON_RPC_RATE_LIMITED`;
  }
  if (/timed? ?out|aborterror|timeout/i.test(combined)) {
    return `${stage}:TON_REQUEST_TIMEOUT`;
  }
  if (/insufficient|not enough|not have enough|low balance|gas fee/i.test(combined)) {
    return `${stage}:WALLET_BALANCE_OR_FEE_INSUFFICIENT`;
  }
  if (/network|failed to fetch|fetch failed|cors|rpc|bridge|connection/i.test(combined)) {
    return `${stage}:TON_NETWORK_OR_RPC_UNAVAILABLE`;
  }
  return `${stage}:UNCLASSIFIED_FAILURE`;
}
