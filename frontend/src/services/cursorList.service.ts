import { apiRequest } from "../lib/api";

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
};

export async function getCursorPage<T>(
  path: string,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<CursorPage<T>> {
  const query = cursor
    ? `?cursor=${encodeURIComponent(cursor)}`
    : "";
  return await apiRequest<CursorPage<T>>(`${path}${query}`, "GET", {
    signal,
  });
}
