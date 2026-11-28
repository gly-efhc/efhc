import {
  useInfiniteQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { getCursorPage } from "../services/cursorList.service";

export function useCursorList<T>(path: string) {
  const queryClient = useQueryClient();
  const queryKey = ["cursor-list", path] as const;
  const query = useInfiniteQuery({
    queryKey,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => (
      getCursorPage<T>(path, pageParam, signal)
    ),
    getNextPageParam: (lastPage) => (
      lastPage.next_cursor ?? undefined
    ),
  });
  const items = query.data?.pages.flatMap((page) => page.items) || [];
  const cursor = query.data?.pages.at(-1)?.next_cursor || null;
  const done = !query.hasNextPage;

  const reset = () => {
    void queryClient.resetQueries({ queryKey });
  };
  const loadMore = async () => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      await query.fetchNextPage();
    }
  };

  return {
    items,
    cursor,
    loading: query.isLoading || query.isFetchingNextPage,
    done,
    loadMore,
    reset,
  };
}
