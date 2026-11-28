import { ApiError } from "./api";
import {
  ADMIN_ACCESS_PATH,
  adminApiRequest,
} from "./api/generated/adminSeams";
import { parseGlobalId, type GlobalId } from "../types/identity";

export type AdminAccess = Readonly<{
  global_id: GlobalId;
  role: string;
}>;

export async function fetchAdminAccess(): Promise<AdminAccess | null> {
  try {
    const raw = await adminApiRequest<unknown>(ADMIN_ACCESS_PATH, "GET");
    if (!raw || typeof raw !== "object") {
      throw new Error("ADMIN_ACCESS_RESPONSE_INVALID");
    }
    const record = raw as Record<string, unknown>;
    if (typeof record.role !== "string" || !record.role.trim()) {
      throw new Error("ADMIN_ACCESS_ROLE_INVALID");
    }
    return {
      global_id: parseGlobalId(record.global_id),
      role: record.role.trim(),
    };
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return null;
    }
    throw error;
  }
}
