import { useMutation } from "@tanstack/react-query";

import {
  downloadAdminLogExport,
  type AdminLogExportFormat,
  type AdminLogExportRows,
  type AdminLogExportScope,
} from "../services/adminLogExport.service";

type AdminLogExportRequest = {
  scope: AdminLogExportScope;
  format: AdminLogExportFormat;
  rows: AdminLogExportRows;
  globalId?: string | null;
};

export function useAdminLogExport() {
  return useMutation({
    mutationFn: ({ scope, format, rows, globalId }: AdminLogExportRequest) =>
      downloadAdminLogExport(scope, format, rows, globalId),
  });
}
