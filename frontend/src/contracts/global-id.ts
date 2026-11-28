/**
 * Изолированный wire-контракт канонического Global ID.
 *
 * Модуль не переключает действующие routes. Он фиксирует DTO и
 * runtime-границы для будущего перехода API на `global_id`.
 */

import {
  type GlobalId,
  globalIdFromApi,
  globalIdToApi,
} from "../types/identity";

export const GLOBAL_ID_API_FIELD = "global_id" as const;
export const GLOBAL_ID_OPENAPI_FORMAT = "efhc-global-id" as const;
export const GLOBAL_ID_OPENAPI_PATTERN = "^[0-9]{10}$" as const;
export const GLOBAL_ID_API_EXAMPLE = "0000000001" as const;

export type GlobalIdRequestDto = Readonly<{
  global_id: GlobalId;
}>;

export type GlobalIdResponseDto = Readonly<{
  global_id: GlobalId;
}>;

function requireExactEnvelope(
  value: unknown,
): Readonly<Record<string, unknown>> {
  if (
    typeof value !== "object" ||
    value === null ||
    Array.isArray(value)
  ) {
    throw new TypeError("Global ID envelope должен быть объектом.");
  }
  const record = value as Readonly<Record<string, unknown>>;
  const keys = Object.keys(record);
  if (keys.length !== 1 || keys[0] !== GLOBAL_ID_API_FIELD) {
    throw new TypeError(
      "Global ID envelope должен содержать только поле global_id.",
    );
  }
  return record;
}

export function decodeGlobalIdRequest(
  value: unknown,
): GlobalIdRequestDto {
  const record = requireExactEnvelope(value);
  return {
    global_id: globalIdFromApi(record[GLOBAL_ID_API_FIELD]),
  };
}

export function decodeGlobalIdResponse(
  value: unknown,
): GlobalIdResponseDto {
  const record = requireExactEnvelope(value);
  return {
    global_id: globalIdFromApi(record[GLOBAL_ID_API_FIELD]),
  };
}

export function encodeGlobalIdRequest(
  value: GlobalIdRequestDto,
): Readonly<{ global_id: string }> {
  return {
    global_id: globalIdToApi(value.global_id),
  };
}

export function encodeGlobalIdResponse(
  value: GlobalIdResponseDto,
): Readonly<{ global_id: string }> {
  return {
    global_id: globalIdToApi(value.global_id),
  };
}
