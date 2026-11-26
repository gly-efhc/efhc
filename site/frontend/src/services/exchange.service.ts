import { apiRequest } from "../lib/api";
import {
  EXCHANGE_CONVERT_PATH,
  EXCHANGE_PREVIEW_PATH,
  type ExchangeConvertResponse,
  type ExchangePreviewResponse,
} from "../lib/api/generated/economicUserSeams";
import {
  ensureExchangeConvertRequest,
  parseExchangeConvertResponse,
  parseExchangePreviewResponse,
} from "../lib/api/generated/economicUserSeamValidators";

export async function getExchangePreview(): Promise<
  ExchangePreviewResponse
> {
  const raw = await apiRequest<unknown>(
    `${EXCHANGE_PREVIEW_PATH}?fresh=true`,
    "GET",
  );
  return parseExchangePreviewResponse(raw);
}

export async function convertExchange(args: {
  amountKwh: string;
  idempotencyKey: string;
  beforeSend?: () => boolean;
}): Promise<ExchangeConvertResponse> {
  const body = ensureExchangeConvertRequest({
    amount_kwh: args.amountKwh,
  });
  const raw = await apiRequest<unknown>(EXCHANGE_CONVERT_PATH, "POST", {
    idempotencyKey: args.idempotencyKey,
    beforeSend: args.beforeSend,
    body,
  });
  return parseExchangeConvertResponse(raw);
}
