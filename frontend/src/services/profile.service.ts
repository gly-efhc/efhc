import { z } from "zod";

import { apiRequest } from "../lib/api";
import { transportRawRequest } from "../data/transport";
import { getAuthAuthorizationHeader, getAuthSessionRevision } from "../lib/auth-session";
import { getTelegramWebApp } from "../lib/telegram";
import { parseGlobalId } from "../types/identity";
import type { DbId } from "../types/db-id";
import { dbIdSchema } from "../lib/api/db-id";

export const walletItemSchema = z.object({
  id: dbIdSchema,
  wallet_address: z.string().min(1),
  // Internal transport/history metadata only. Never use as bound-address UI identity.
  wallet_app: z.string().nullable().optional().transform((value) => value ?? null),
  is_primary: z.boolean(),
  is_active: z.boolean(),
  proof_verified: z.boolean(),
  is_project_test: z.boolean().optional().default(false),
  created_at: z.string().nullable().optional().transform(
    (value) => value ?? "",
  ),
});

export const walletsMeSchema = z.object({
  is_connected: z.boolean(),
  wallets: z.array(walletItemSchema),
});

export const balanceHistoryItemSchema = z.object({
  id: dbIdSchema,
  amount_efhc: z.string().min(1),
  direction: z.enum(["credit", "debit"]),
  balance_type: z.enum(["main", "bonus"]),
  reason: z.string().min(1),
  created_at: z.string().min(1),
});

export const balanceHistoryPageSchema = z.object({
  items: z.array(balanceHistoryItemSchema),
  next_cursor: z.string().nullable(),
});

export const withdrawHistoryItemSchema = z.object({
  id: dbIdSchema,
  global_id: z.string().transform((value) => parseGlobalId(value)),
  amount: z.string().min(1),
  status: z.string().min(1),
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
});

export const withdrawHistoryPageSchema = z.object({
  items: z.array(withdrawHistoryItemSchema),
  next_cursor: z.string().nullable(),
});

export const exchangeHistoryItemSchema = z.object({
  id: dbIdSchema,
  created_at: z.string().min(1),
  amount_kwh: z.string().min(1),
  amount_efhc: z.string().min(1),
  reason: z.string().min(1),
});

export const exchangeHistoryPageSchema = z.object({
  items: z.array(exchangeHistoryItemSchema),
  next_cursor: z.string().nullable(),
});

export const profilePhotoSourceSchema = z.object({
  provider: z.string().min(1),
  avatar_url: z.string().url().refine((value) => value.startsWith("https://")),
  is_primary: z.boolean().optional().default(false),
});

export const profilePhotoSourcesSchema = z.object({
  items: z.array(profilePhotoSourceSchema),
});

export type WalletItem = z.infer<typeof walletItemSchema>;
export type WalletsMeOut = z.infer<typeof walletsMeSchema>;
export type BalanceHistoryItem = z.infer<
  typeof balanceHistoryItemSchema
>;
export type BalanceHistoryPage = z.infer<
  typeof balanceHistoryPageSchema
>;
export type WithdrawHistoryItem = z.infer<
  typeof withdrawHistoryItemSchema
>;
export type WithdrawHistoryPage = z.infer<
  typeof withdrawHistoryPageSchema
>;
export type ExchangeHistoryItem = z.infer<
  typeof exchangeHistoryItemSchema
>;
export type ExchangeHistoryPage = z.infer<
  typeof exchangeHistoryPageSchema
>;
export type ProfilePhotoSource = z.infer<typeof profilePhotoSourceSchema>;
export type ProfilePhotoSources = z.infer<typeof profilePhotoSourcesSchema>;

export async function getProfilePhotoSources(
  signal?: AbortSignal,
): Promise<ProfilePhotoSources> {
  const raw = await apiRequest<unknown>("/auth/profile-photos", "GET", { signal });
  return profilePhotoSourcesSchema.parse(raw);
}

export async function makePrimaryWallet(
  walletId: DbId,
): Promise<unknown> {
  return await apiRequest<unknown>(
    `/wallets/${walletId}/make-primary`,
    "POST",
  );
}

export async function deleteWallet(
  walletId: DbId,
): Promise<unknown> {
  return await apiRequest<unknown>(
    `/wallets/${walletId}`,
    "DELETE",
  );
}

export async function getProfileWallets<
  T = WalletsMeOut,
>(signal?: AbortSignal): Promise<T> {
  const raw = await apiRequest<unknown>("/wallets/me", "GET", {
    signal,
  });
  return walletsMeSchema.parse(raw) as T;
}

export async function getProfileBalanceHistoryPage(args?: {
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}): Promise<BalanceHistoryPage> {
  const query = new URLSearchParams();
  query.set("limit", String(args?.limit ?? 20));
  if (args?.cursor) query.set("cursor", args.cursor);
  const raw = await apiRequest<unknown>(
    `/wallets/balance-history?${query.toString()}`,
    "GET",
    { signal: args?.signal },
  );
  return balanceHistoryPageSchema.parse(raw);
}


export async function getProfileExchangeHistoryPage(args?: {
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}): Promise<ExchangeHistoryPage> {
  const query = new URLSearchParams();
  query.set("limit", String(args?.limit ?? 50));
  if (args?.cursor) query.set("cursor", args.cursor);
  const raw = await apiRequest<unknown>(
    `/exchange/history?${query.toString()}`,
    "GET",
    { signal: args?.signal },
  );
  return exchangeHistoryPageSchema.parse(raw);
}

export async function getProfileWithdrawHistoryPage(args?: {
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}): Promise<WithdrawHistoryPage> {
  const query = new URLSearchParams();
  query.set("limit", String(args?.limit ?? 20));
  if (args?.cursor) query.set("cursor", args.cursor);
  const raw = await apiRequest<unknown>(
    `/withdraw/list/me?${query.toString()}`,
    "GET",
    { signal: args?.signal },
  );
  return withdrawHistoryPageSchema.parse(raw);
}

export async function getProfileBalanceHistory<
  T = BalanceHistoryPage,
>(
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<T> {
  return await getProfileBalanceHistoryPage({
    cursor,
    signal,
  }) as T;
}

export async function getProfileWithdrawHistory<
  T = WithdrawHistoryPage,
>(
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<T> {
  return await getProfileWithdrawHistoryPage({
    cursor,
    signal,
  }) as T;
}

const PROFILE_EXPORT_MAX_PAGES = 5000;

async function readAllCursorPages<T extends { next_cursor: string | null }>(
  readPage: (cursor: string | null) => Promise<T>,
  readItems: (page: T) => unknown[],
): Promise<unknown[]> {
  const out: unknown[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  for (let pageIndex = 0; pageIndex < PROFILE_EXPORT_MAX_PAGES; pageIndex += 1) {
    const page = await readPage(cursor);
    out.push(...readItems(page));
    const next = page.next_cursor || null;
    if (!next) return out;
    if (seen.has(next)) throw new Error("profile_export_cursor_loop");
    seen.add(next);
    cursor = next;
  }
  throw new Error("profile_export_page_limit");
}

function csvSafeCell(value: unknown): string {
  const raw = value === null || value === undefined ? "" : String(value);
  const protectedValue = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${protectedValue.replace(/"/g, '""')}"`;
}

function csvRow(values: unknown[]): string {
  return values.map(csvSafeCell).join(",");
}

export async function downloadProfileOperationsCsv(args: {
  totalBalance: string;
  mainBalance: string;
  bonusBalance: string;
}): Promise<{ ledger: number; exchanges: number; withdrawals: number }> {
  const [ledgerRaw, exchangesRaw, withdrawalsRaw] = await Promise.all([
    readAllCursorPages(
      (cursor) => getProfileBalanceHistoryPage({ cursor, limit: 100 }),
      (page) => page.items,
    ),
    readAllCursorPages(
      (cursor) => getProfileExchangeHistoryPage({ cursor, limit: 200 }),
      (page) => page.items,
    ),
    readAllCursorPages(
      (cursor) => getProfileWithdrawHistoryPage({ cursor, limit: 100 }),
      (page) => page.items,
    ),
  ]);

  const ledger = ledgerRaw as BalanceHistoryItem[];
  const exchanges = exchangesRaw as ExchangeHistoryItem[];
  const withdrawals = withdrawalsRaw as WithdrawHistoryItem[];
  const exportedAt = new Date().toISOString();

  const rows: unknown[][] = [
    [
      "record_type",
      "created_at",
      "id",
      "direction",
      "balance_type",
      "amount_efhc",
      "amount_kwh",
      "reason",
      "status",
    ],
    ["balance_snapshot", exportedAt, "", "", "total", args.totalBalance, "", "current_balance", ""],
    ["balance_snapshot", exportedAt, "", "", "main", args.mainBalance, "", "current_balance", ""],
    ["balance_snapshot", exportedAt, "", "", "bonus", args.bonusBalance, "", "current_balance", ""],
    ...ledger.map((item) => [
      "balance_ledger",
      item.created_at,
      item.id,
      item.direction,
      item.balance_type,
      item.amount_efhc,
      "",
      item.reason,
      "",
    ]),
    ...exchanges.map((item) => [
      "exchange",
      item.created_at,
      item.id,
      "credit",
      "main",
      item.amount_efhc,
      item.amount_kwh,
      item.reason,
      "",
    ]),
    ...withdrawals.map((item) => [
      "withdraw_request",
      item.created_at,
      item.id,
      "",
      "main",
      item.amount,
      "",
      "withdraw_request",
      item.status,
    ]),
  ];

  const csv = "\uFEFF" + rows.map(csvRow).join("\r\n") + "\r\n";
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    const day = exportedAt.slice(0, 10);
    anchor.href = url;
    anchor.download = `EFHC_operations_${day}.csv`;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return {
    ledger: ledger.length,
    exchanges: exchanges.length,
    withdrawals: withdrawals.length,
  };
}

export const profileHistoryItemSchema = z.object({
  id: dbIdSchema,
  source: z.string().min(1),
  kind: z.string().min(1),
  occurred_at: z.string().min(1),
  executed_at: z.string().min(1).nullable().optional(),
  panel_public_id: z.string().nullable().optional(),
  status: z.string().nullable(),
  direction: z.string().nullable(),
  balance_type: z.string().nullable(),
  amount_efhc: z.string().nullable(),
  amount_asset: z.string().nullable(),
  asset: z.string().nullable(),
  reason: z.string().nullable(),
});

export const profileHistoryPageSchema = z.object({
  items: z.array(profileHistoryItemSchema).max(50),
  next_cursor: z.string().nullable(),
  page_size: z.literal(50),
});

export type ProfileHistoryItem = z.infer<typeof profileHistoryItemSchema>;
export type ProfileHistoryPage = z.infer<typeof profileHistoryPageSchema>;

export async function getUnifiedProfileHistoryPage(args?: {
  cursor?: string | null;
  signal?: AbortSignal;
}): Promise<ProfileHistoryPage> {
  const query = new URLSearchParams();
  if (args?.cursor) query.set("cursor", args.cursor);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const raw = await apiRequest<unknown>(
    `/profile/history${suffix}`,
    "GET",
    { signal: args?.signal },
  );
  return profileHistoryPageSchema.parse(raw);
}

export type ProfileHistoryExportCategory = "all" | "purchases" | "exchange" | "withdraw" | "bonuses" | "panels";

const profileExportGrantSchema = z.object({
  ticket: z.string().regex(/^[A-Za-z0-9_-]{43}$/),
  filename: z.string().regex(/^EFHC_[a-z]+_\d{4}-\d{2}-\d{2}\.(csv|xlsx)$/),
});

export async function downloadProfileHistoryExport(
  format: "csv" | "xlsx",
  category: ProfileHistoryExportCategory,
): Promise<ProfileDownloadOutcome> {
  if (profileDownloadInFlight) return "busy";
  profileDownloadInFlight = true;
  try {
    return await prepareProfileDownload(format, category);
  } finally {
    profileDownloadInFlight = false;
  }
}

export type ProfileDownloadOutcome = "requested" | "cancelled" | "unknown" | "busy" | "session_changed";
let profileDownloadInFlight = false;

async function prepareProfileDownload(
  format: "csv" | "xlsx",
  category: ProfileHistoryExportCategory,
): Promise<ProfileDownloadOutcome> {
  const actor = getAuthAuthorizationHeader();
  const revision = getAuthSessionRevision();
  if (!actor) throw new Error("profile_history_export_auth_required");
  const query = new URLSearchParams({ category, format });
  const response = await transportRawRequest(
    `/profile/history/export-ticket?${query.toString()}`, "POST",
  );
  if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("profile_history_export_failed");
  }
  const grant = profileExportGrantSchema.parse(await response.json());
  if (getAuthAuthorizationHeader() !== actor || getAuthSessionRevision() !== revision) return "session_changed";
  if (!grant.filename.startsWith(`EFHC_${category}_`) || !grant.filename.endsWith(`.${format}`)) {
    throw new Error("profile_history_export_invalid_filename");
  }
  const url = new URL("export-download", response.url);
  if (url.protocol !== "https:" && !(
    url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)
  )) throw new Error("profile_history_export_invalid_origin");
  url.searchParams.set("ticket", grant.ticket);
  const webApp = getTelegramWebApp();
  if (url.protocol === "https:" && webApp?.initData &&
      typeof webApp.downloadFile === "function" &&
      (typeof webApp.isVersionAtLeast !== "function" || webApp.isVersionAtLeast("8.0"))) {
    return await new Promise<ProfileDownloadOutcome>((resolve, reject) => {
      // Telegram acknowledges the request, not physical file persistence.
      // Cancellation or an unknown result must never start a second adapter.
      let settled = false;
      const settle = (result: ProfileDownloadOutcome) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve(result);
      };
      const timer = window.setTimeout(() => settle("unknown"), 120_000);
      try {
        webApp.downloadFile({ url: url.href, file_name: grant.filename }, (accepted: unknown) => {
          settle(accepted === true ? "requested" : accepted === false ? "cancelled" : "unknown");
        });
      } catch (error) {
        if (!settled) {
          settled = true;
          window.clearTimeout(timer);
          reject(error);
        }
      }
    });
  }
  const anchor = document.createElement("a");
  anchor.href = url.href;
  anchor.download = grant.filename;
  anchor.rel = "noopener noreferrer";
  anchor.referrerPolicy = "no-referrer";
  document.body.appendChild(anchor);
  try { anchor.click(); } finally { anchor.remove(); }
  return "requested";
}
