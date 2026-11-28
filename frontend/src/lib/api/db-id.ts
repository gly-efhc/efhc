import { z } from "zod";

import {
  DB_ID_PATTERN,
  POSTGRES_BIGINT_MAX_TEXT,
  type DbId,
} from "../../types/db-id";

const canonicalDbIdSchema = z
  .string()
  .regex(DB_ID_PATTERN)
  .refine(
    (value) =>
      value.length < POSTGRES_BIGINT_MAX_TEXT.length ||
      (value.length === POSTGRES_BIGINT_MAX_TEXT.length &&
        value <= POSTGRES_BIGINT_MAX_TEXT),
    "Lifetime ID вне диапазона PostgreSQL BIGINT.",
  )
  .transform((value) => value as DbId);

const legacySafeIntegerDbIdSchema = z
  .number()
  .int()
  .positive()
  .refine(Number.isSafeInteger, "Legacy lifetime ID должен быть safe integer.")
  .transform((value) => String(value) as DbId);

export const dbIdSchema = z.union([
  canonicalDbIdSchema,
  legacySafeIntegerDbIdSchema,
]);
