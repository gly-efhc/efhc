export type ShopReviewAsset = "TON" | "USDT" | "EFHC";
export type ShopReview = { review_id: string; quote: { asset: ShopReviewAsset; amount: string } };
const SCALES = { TON: 9, USDT: 6, EFHC: 8 } as const;
const assetValid = (asset: unknown): asset is ShopReviewAsset =>
  asset === "TON" || asset === "USDT" || asset === "EFHC";

function toAtomic(amount: unknown, asset: ShopReviewAsset): bigint | null {
  if (typeof amount !== "string" || amount.length > 40) return null;
  const match = /^(0|[1-9][0-9]*)(?:\.([0-9]+))?$/.exec(amount);
  if (!match || (match[2]?.length || 0) > SCALES[asset]) return null;
  const atomic = BigInt(match[1] + (match[2] || "").padEnd(SCALES[asset],"0"));
  return atomic > 0n ? atomic : null;
}

export function readShopReview(raw: unknown): ShopReview | null {
  if (!raw || typeof raw !== "object") return null;
  const { review_id, quote } = raw as Record<string, unknown>;
  if (typeof review_id !== "string" || !/^[a-f0-9]{64}$/.test(review_id) || !quote || typeof quote !== "object") return null;
  const { asset, amount } = quote as Record<string, unknown>;
  if (!assetValid(asset) || typeof amount !== "string" || toAtomic(amount,asset) === null) return null;
  return { review_id, quote: { asset, amount } };
}

export function matchesExternalShopReview(
  review: ShopReview, payment: { pay_method: unknown; amount: unknown; external_amount_atomic: unknown; external_decimals: unknown },
) {
  const { asset, amount } = review.quote;
  if (asset === "EFHC" || payment.pay_method !== asset || payment.external_decimals !== SCALES[asset]) return false;
  const reviewed = toAtomic(amount,asset);
  if (reviewed === null || toAtomic(payment.amount,asset) !== reviewed) return false;
  return typeof payment.external_amount_atomic === "string" && /^[1-9][0-9]{0,38}$/.test(payment.external_amount_atomic)
    && BigInt(payment.external_amount_atomic) === reviewed;
}
