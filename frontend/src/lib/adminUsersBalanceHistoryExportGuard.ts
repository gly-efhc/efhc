const GLOBAL_ID_RE = /^\d{10}$/;

export type AdminUsersBalanceHistoryExportScope = {
  selectedGlobalId: string | null | undefined;
  subjectGlobalIds: readonly (string | null | undefined)[];
  /**
   * Canonical route-level owner proof. Cycle0239 proves that
   * GET /admin/users/{global_id}/history applies this Global ID in SQL before
   * cursor/order/limit, so per-row Global ID repetition is not required.
   */
  serverScopedGlobalId?: string | null | undefined;
  /**
   * Alternate row-level proof for any future source that is not already
   * exact-owner server scoped. Kept for backwards-compatible fail-closed use.
   */
  rowGlobalIds?: readonly (string | null | undefined)[];
};

export class AdminUsersBalanceHistoryExportScopeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AdminUsersBalanceHistoryExportScopeError";
  }
}

function requireGlobalId(value: string | null | undefined, label: string): string {
  const normalized = String(value || "").trim();
  if (!GLOBAL_ID_RE.test(normalized)) {
    throw new AdminUsersBalanceHistoryExportScopeError(`${label}_global_id_unproven`);
  }
  return normalized;
}

/**
 * Cycle0238 guard for any future Admin Users → Balance/History export.
 *
 * Current Users/History UI has no Admin export callback. A future export must
 * call this guard only after ownership is proven either by the canonical
 * exact-owner server route or by explicit owner fields on every row.
 * Browser-side inference/filtering of an all-user dataset is forbidden.
 */
export function assertAdminUsersBalanceHistoryExactOneUserExportScope(
  scope: AdminUsersBalanceHistoryExportScope,
): string {
  const selectedGlobalId = requireGlobalId(scope.selectedGlobalId, "selected");

  if (scope.subjectGlobalIds.length !== 1) {
    throw new AdminUsersBalanceHistoryExportScopeError("exactly_one_user_required");
  }

  const subjectGlobalId = requireGlobalId(scope.subjectGlobalIds[0], "subject");
  if (subjectGlobalId !== selectedGlobalId) {
    throw new AdminUsersBalanceHistoryExportScopeError("selected_user_mismatch");
  }

  if (scope.serverScopedGlobalId !== undefined) {
    const serverScopedGlobalId = requireGlobalId(
      scope.serverScopedGlobalId,
      "server_scope",
    );
    if (serverScopedGlobalId !== selectedGlobalId) {
      throw new AdminUsersBalanceHistoryExportScopeError("server_scope_mismatch");
    }
    return selectedGlobalId;
  }

  if (!scope.rowGlobalIds) {
    throw new AdminUsersBalanceHistoryExportScopeError("owner_proof_required");
  }

  for (const rowGlobalIdValue of scope.rowGlobalIds) {
    const rowGlobalId = requireGlobalId(rowGlobalIdValue, "row");
    if (rowGlobalId !== selectedGlobalId) {
      throw new AdminUsersBalanceHistoryExportScopeError("foreign_row_forbidden");
    }
  }

  return selectedGlobalId;
}
