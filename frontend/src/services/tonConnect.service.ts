import { z } from "zod";

import { apiRequest } from "../lib/api";
import { dbIdSchema } from "../lib/api/db-id";

const TonProofPayloadSchema = z.object({
  ton_proof_payload: z.string().min(1),
  payload_token: z.string().min(1),
  expires_at: z.string().min(1),
  domain: z.string().min(1),
});

const TonProofCheckSchema = z.object({
  accepted: z.boolean(),
  cryptographically_verified: z.boolean(),
});

const WalletConnectSchema = z.object({
  wallet_id: dbIdSchema,
  wallet_address: z.string().min(1),
  is_connected: z.boolean(),
});

export type TonProofPayloadResponse = z.infer<
  typeof TonProofPayloadSchema
>;
export type TonProofCheckResponse = z.infer<typeof TonProofCheckSchema>;
export type WalletConnectResponse = z.infer<typeof WalletConnectSchema>;

export async function getTonProofPayload(): Promise<
  TonProofPayloadResponse
> {
  const raw = await apiRequest<unknown>(
    "/wallets/tonconnect/proof-payload",
    "GET",
  );
  return TonProofPayloadSchema.parse(raw);
}

export async function checkTonProofEnvelope(
  body: Record<string, unknown>,
): Promise<TonProofCheckResponse> {
  const raw = await apiRequest<unknown>(
    "/wallets/tonconnect/check-proof",
    "POST",
    { body },
  );
  return TonProofCheckSchema.parse(raw);
}

export async function connectVerifiedTonWallet(args: {
  body: Record<string, unknown>;
  idempotencyKey: string;
}): Promise<WalletConnectResponse> {
  const raw = await apiRequest<unknown>(
    "/wallets/connect",
    "POST",
    {
      idempotencyKey: args.idempotencyKey,
      body: args.body,
    },
  );
  return WalletConnectSchema.parse(raw);
}
