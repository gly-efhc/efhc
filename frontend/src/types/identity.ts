/**
 * Канонические frontend-типы идентичности EFHC.
 *
 * `GlobalId` — строка из десяти ASCII-цифр.
 * `TelegramId` — положительное безопасное целое Telegram provider.
 * Типы нельзя присваивать друг другу даже при совпадении цифр.
 */

declare const globalIdBrand: unique symbol;
declare const telegramIdBrand: unique symbol;

export type GlobalId = string & {
  readonly [globalIdBrand]: "GlobalId";
};

export type TelegramId = number & {
  readonly [telegramIdBrand]: "TelegramId";
};

export const GLOBAL_ID_PATTERN = /^[0-9]{10}$/;
export const GLOBAL_ID_ZERO = "0000000000";
export const TG_ID_MIN = 1;

export type GlobalIdErrorCode =
  | "global_id.frontend.type"
  | "global_id.frontend.format"
  | "global_id.frontend.zero";

export type TelegramIdErrorCode =
  | "tg_id.frontend.type"
  | "tg_id.frontend.integer"
  | "tg_id.frontend.range";

export class GlobalIdValueError extends Error {
  readonly code: GlobalIdErrorCode;
  readonly field = "global_id";

  constructor(message: string, code: GlobalIdErrorCode) {
    super(message);
    this.name = "GlobalIdValueError";
    this.code = code;
  }

  asObject(): Readonly<{
    field: "global_id";
    code: GlobalIdErrorCode;
    message: string;
  }> {
    return {
      field: this.field,
      code: this.code,
      message: this.message,
    };
  }
}

export class TelegramIdValueError extends Error {
  readonly code: TelegramIdErrorCode;
  readonly field = "tg_id";

  constructor(message: string, code: TelegramIdErrorCode) {
    super(message);
    this.name = "TelegramIdValueError";
    this.code = code;
  }

  asObject(): Readonly<{
    field: "tg_id";
    code: TelegramIdErrorCode;
    message: string;
  }> {
    return {
      field: this.field,
      code: this.code,
      message: this.message,
    };
  }
}

export function isGlobalId(value: unknown): value is GlobalId {
  return (
    typeof value === "string" &&
    GLOBAL_ID_PATTERN.test(value) &&
    value !== GLOBAL_ID_ZERO
  );
}

export function parseGlobalId(value: unknown): GlobalId {
  if (typeof value !== "string") {
    throw new GlobalIdValueError(
      "Global ID должен быть строкой.",
      "global_id.frontend.type",
    );
  }
  if (!GLOBAL_ID_PATTERN.test(value)) {
    throw new GlobalIdValueError(
      "Global ID должен содержать ровно десять ASCII-цифр.",
      "global_id.frontend.format",
    );
  }
  if (value === GLOBAL_ID_ZERO) {
    throw new GlobalIdValueError(
      "Global ID 0000000000 запрещён.",
      "global_id.frontend.zero",
    );
  }
  return value as GlobalId;
}

export function isTelegramId(value: unknown): value is TelegramId {
  return (
    typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value >= TG_ID_MIN
  );
}

export function parseTelegramId(value: unknown): TelegramId {
  if (typeof value !== "number") {
    throw new TelegramIdValueError(
      "Telegram ID должен быть числом provider.",
      "tg_id.frontend.type",
    );
  }
  if (!Number.isSafeInteger(value)) {
    throw new TelegramIdValueError(
      "Telegram ID должен быть безопасным целым числом.",
      "tg_id.frontend.integer",
    );
  }
  if (value < TG_ID_MIN) {
    throw new TelegramIdValueError(
      "Telegram ID должен быть положительным.",
      "tg_id.frontend.range",
    );
  }
  return value as TelegramId;
}

export const globalIdFromApi = parseGlobalId;
export const telegramIdFromProvider = parseTelegramId;

export function globalIdToApi(value: GlobalId): string {
  return value;
}

export function telegramIdToProvider(value: TelegramId): number {
  return value;
}

export function formatGlobalId(value: GlobalId): string {
  return value;
}

export function formatTelegramId(value: TelegramId): string {
  return String(value);
}
