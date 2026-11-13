import { apiRequest } from "../lib/api";
import { balanceHistoryItemSchema } from "./profile.service";
import {
  WITHDRAW_CANCEL_PATH,
  WITHDRAW_DETAIL_PATH,
  WITHDRAW_LIST_PATH,
  WITHDRAW_REQUEST_PATH,
  type WithdrawDetail,
  type WithdrawItem,
  type WithdrawOutcomeBundle,
  type WithdrawPageResponse,
} from "../lib/api/generated/economicUserSeams";
import {
  ensureWithdrawRequestCreate,
  parseWithdrawDetail,
  parseWithdrawOutcomeBundle,
  parseWithdrawPageResponse,
} from "../lib/api/generated/economicUserSeamValidators";
import type { DbId } from "../types/db-id";

export type WalletHistoryItem = {
  id: DbId;
  amount_efhc: string;
  direction: "credit" | "debit";
  balance_type: "main" | "bonus";
  reason: string;
  created_at: string;
};

export type WalletHistoryOut = {
  items: WalletHistoryItem[];
};

export async function getWithdrawalsPage(args: {
  limit?: number;
  cursor?: string | null;
  statusFilter?: string;
  signal?: AbortSignal;
}): Promise<WithdrawPageResponse> {
  const query = new URLSearchParams();
  query.set("limit", String(args.limit || 100));
  if (args.cursor) query.set("cursor", args.cursor);
  if (args.statusFilter && args.statusFilter !== "all") {
    query.set("status_filter", args.statusFilter);
  }
  const raw = await apiRequest<unknown>(
    `${WITHDRAW_LIST_PATH}?${query.toString()}`,
    "GET",
    { signal: args.signal },
  );
  return parseWithdrawPageResponse(raw);
}

export async function getWithdrawDetail(
  requestId: DbId,
  signal?: AbortSignal,
): Promise<WithdrawDetail> {
  const raw = await apiRequest<unknown>(
    WITHDRAW_DETAIL_PATH.replace("{request_id}", String(requestId)),
    "GET",
    { signal },
  );
  return parseWithdrawDetail(raw);
}

export async function getWalletBalanceHistory(
  limit = 5,
  signal?: AbortSignal,
): Promise<WalletHistoryItem[]> {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  const out = await apiRequest<WalletHistoryOut>(
    `/wallets/balance-history?${query.toString()}`,
    "GET",
    { signal },
  );
  return balanceHistoryItemSchema.array().parse(out.items);
}

export async function createWithdrawRequest(args: {
  amount: string;
  walletId: DbId;
  idempotencyKey: string;
}): Promise<WithdrawDetail> {
  const body = ensureWithdrawRequestCreate({
    amount: args.amount,
    wallet_id: args.walletId,
  });
  const raw = await apiRequest<unknown>(WITHDRAW_REQUEST_PATH, "POST", {
    idempotencyKey: args.idempotencyKey,
    body,
  });
  return parseWithdrawDetail(raw);
}

export async function cancelWithdrawRequest(args: {
  requestId: DbId;
  idempotencyKey: string;
}): Promise<WithdrawDetail> {
  const raw = await apiRequest<unknown>(
    WITHDRAW_CANCEL_PATH.replace(
      "{request_id}",
      String(args.requestId),
    ),
    "POST",
    {
      idempotencyKey: args.idempotencyKey,
      body: {},
    },
  );
  return parseWithdrawDetail(raw);
}

export async function getWithdrawOutcome(
  requestId: DbId,
  signal?: AbortSignal,
): Promise<WithdrawOutcomeBundle> {
  const raw = await apiRequest<unknown>(
    `/api/v1/me/withdraw-outcomes/${String(requestId)}`,
    "GET",
    { signal },
  );
  return parseWithdrawOutcomeBundle(raw);
}

export type { WithdrawItem };
