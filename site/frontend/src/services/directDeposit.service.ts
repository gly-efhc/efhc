import { z } from "zod";

import { apiRequest } from "../lib/api";
import { getProfileBalanceHistoryPage } from "./profile.service";

const directDepositOpenSchema = z.object({
  purpose: z.literal("direct_efhc_jetton_deposit"),
  asset: z.literal("EFHC"),
  receiver_owner_address: z.string().min(1),
  jetton_master_address: z.string().min(1),
  jetton_decimals: z.literal(8),
  forward_payload_text: z.string().regex(/^EFHC:GID:\d{10}$/),
  fee_message_ton_amount: z.string().min(1),
  forward_ton_amount: z.string().min(1),
  memo_binding: z.literal("global_id"),
});

export type DirectDepositOpen = z.infer<typeof directDepositOpenSchema>;

export type DirectDepositStatus = {
  state: "checking" | "confirmed";
  amount_efhc: string | null;
  created_at: string | null;
};

export async function openDirectDeposit(): Promise<DirectDepositOpen> {
  const raw = await apiRequest<unknown>("/deposit/direct-open", "GET");
  return directDepositOpenSchema.parse(raw);
}

const sharedDepositCheckSchema = z.object({
  ok: z.literal(true),
  state: z.enum(["checked", "busy", "cooldown"]),
});

/** The server verifies the global treasury inbox, never a client-supplied tx. */
export async function runSharedDepositCheck() {
  const result = await apiRequest<unknown>("/deposit/direct-check", "POST");
  return sharedDepositCheckSchema.parse(result);
}

export async function readDirectDepositStatus(
  openedAt: string,
  signal?: AbortSignal,
): Promise<DirectDepositStatus> {
  const page = await getProfileBalanceHistoryPage({
    limit: 50,
    signal,
  });
  const openedMs = Date.parse(openedAt);
  const item = page.items.find((row) => {
    if (
      row.reason !== "efhc_external_deposit"
      && row.reason !== "efhc_jetton_nomemo_wallet_bound"
    ) {
      return false;
    }
    const createdMs = Date.parse(row.created_at);
    return Number.isFinite(createdMs)
      && Number.isFinite(openedMs)
      && createdMs >= openedMs;
  });
  if (!item) {
    return {
      state: "checking",
      amount_efhc: null,
      created_at: null,
    };
  }
  return {
    state: "confirmed",
    amount_efhc: item.amount_efhc,
    created_at: item.created_at,
  };
}
