import { useEffect, useMemo, useRef, useState } from "react";

const WORKER_THRESHOLD = 10_000;

type FilterKind = "logs" | "users";

type WorkerResponse = {
  id: number;
  indices: number[];
};

export function useLargeAdminFilter<T>(
  items: T[],
  kind: FilterKind,
  criteria: Record<string, unknown>,
  syncFilter: (item: T) => boolean,
) {
  const requestId = useRef(0);
  const [workerIndices, setWorkerIndices] = useState<
    number[] | null
  >(null);
  const criteriaKey = JSON.stringify(criteria);

  useEffect(() => {
    const unavailable = typeof Worker === "undefined";
    if (items.length <= WORKER_THRESHOLD || unavailable) {
      setWorkerIndices(null);
      return;
    }
    const worker = new Worker(
      new URL("../../workers/adminFilter.worker.ts", import.meta.url),
    );
    const id = requestId.current + 1;
    requestId.current = id;
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      if (event.data.id === requestId.current) {
        setWorkerIndices(event.data.indices);
      }
    };
    worker.postMessage({ criteria, id, items, kind });
    return () => worker.terminate();
  }, [criteriaKey, items, kind]);

  const filtered = useMemo(() => {
    if (items.length > WORKER_THRESHOLD && workerIndices) {
      return workerIndices
        .map((index) => items[index])
        .filter((item): item is T => Boolean(item));
    }
    if (items.length > WORKER_THRESHOLD && !workerIndices) return [];
    return items.filter(syncFilter);
  }, [items, syncFilter, workerIndices]);

  return {
    filtered,
    processing: items.length > WORKER_THRESHOLD && !workerIndices,
    workerActive: items.length > WORKER_THRESHOLD,
  };
}
