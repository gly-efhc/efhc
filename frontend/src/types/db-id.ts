/**
 * Канонический frontend-тип PostgreSQL lifetime identifier.
 *
 * Новые API передают lifetime IDs как decimal strings. Legacy safe-integer
 * input временно принимается только для совместимости со старым payload.
 */

declare const dbIdBrand: unique symbol;

export type DbId = string & {
  readonly [dbIdBrand]: "DbId";
};

export const DB_ID_PATTERN = /^[1-9][0-9]{0,18}$/;
export const POSTGRES_BIGINT_MAX_TEXT = "9223372036854775807";

function isWithinPostgresBigint(value: string): boolean {
  if (value.length < POSTGRES_BIGINT_MAX_TEXT.length) return true;
  if (value.length > POSTGRES_BIGINT_MAX_TEXT.length) return false;
  return value <= POSTGRES_BIGINT_MAX_TEXT;
}

export function isDbId(value: unknown): value is DbId {
  return (
    typeof value === "string" &&
    DB_ID_PATTERN.test(value) &&
    isWithinPostgresBigint(value)
  );
}

export function dbIdFromApi(value: unknown): DbId {
  if (isDbId(value)) return value;
  if (
    typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value > 0
  ) {
    return String(value) as DbId;
  }
  throw new TypeError(
    "Lifetime ID должен быть положительной decimal string в диапазоне PostgreSQL BIGINT.",
  );
}

export function dbIdToApi(value: DbId): string {
  if (!isDbId(value)) {
    throw new TypeError("Некорректный lifetime ID.");
  }
  return value;
}
