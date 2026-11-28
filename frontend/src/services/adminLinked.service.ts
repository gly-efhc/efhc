import { z } from "zod";
import { requireBankSnapshot } from "../lib/adminBankSnapshot";
export { readAdminDisplay } from "../lib/adminReadCache";

import {
  apiRequest,
  type ApiRequestOptions,
  type HttpMethod,
} from "../lib/api";
import {
  parseAdminBankBalanceResponse,
  parseAdminBankMutationResponse,
  parseAdminReferralSummaryResponse,
  parseAdminWithdrawalListResponse,
  parseAdminWithdrawActionResponse,
  parseAdminWithdrawOutcomePreviewResponse,
  parseAdminWithdrawPayoutReservationResponse,
} from "../lib/api/generated/adminSeamValidators";

export type AdminLinkedRequest = {
  path: string;
  method: HttpMethod;
  options?: ApiRequestOptions;
};

const JsonResponseSchema = z.union([
  z.object({}).passthrough(),
  z.array(z.unknown()),
  z.string(),
  z.number(),
  z.boolean(),
  z.null(),
  z.undefined(),
]);

function cleanPath(path: string): string {
  return path.split("?", 1)[0].replace(/\/$/, "") || "/";
}

function parseAdminLinkedResponse(
  path: string,
  method: HttpMethod,
  value: unknown,
): unknown {
  const clean = cleanPath(path);
  if (method === "GET" && clean === "/admin/reports/overview") return requireBankSnapshot(value);

  if (method === "GET" && clean === "/admin/bank/balance") {
    return parseAdminBankBalanceResponse(value);
  }
  if (
    method === "GET"
    && clean === "/admin/withdrawals"
  ) {
    return parseAdminWithdrawalListResponse(value);
  }
  if (
    method === "GET"
    && clean === "/admin/referrals/summary"
  ) {
    return parseAdminReferralSummaryResponse(value);
  }
  if (
    method === "GET"
    && /^\/admin\/withdrawals\/[^/]+\/outcome-preview$/.test(clean)
  ) {
    return parseAdminWithdrawOutcomePreviewResponse(value);
  }
  if (
    method === "GET"
    && /^\/admin\/withdrawals\/[^/]+\/payout-reservation$/.test(clean)
  ) {
    return parseAdminWithdrawPayoutReservationResponse(value);
  }
  if (
    method === "POST"
    && /^\/admin\/withdrawals\/[^/]+\/(approve|reject|mark-paid)$/.test(clean)
  ) {
    return parseAdminWithdrawActionResponse(value);
  }
  if (
    method === "POST"
    && /^\/admin\/withdrawals\/[^/]+\/payout-reserve$/.test(clean)
  ) {
    return parseAdminWithdrawPayoutReservationResponse(value);
  }
  if (
    method === "POST"
    && (clean === "/admin/bank/mint" || clean === "/admin/bank/burn")
  ) {
    return parseAdminBankMutationResponse(value);
  }

  return JsonResponseSchema.parse(value);
}

export async function adminLinkedRequest<T>(
  request: AdminLinkedRequest,
): Promise<T> {
  const raw = await apiRequest<unknown>(
    request.path,
    request.method,
    request.options,
  );
  return parseAdminLinkedResponse(
    request.path,
    request.method,
    raw,
  ) as T;
}
