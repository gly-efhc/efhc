import { useEffect, useMemo, useRef, useState } from "react";

import { FAQ_SEARCH_RESULT_LIMIT } from "../../data/faq/searchContract";
import type {
  FaqCatalog,
  FaqSearchHit,
} from "../../data/faq/types";
import { searchFaq } from "../../data/faq/utils";

type WorkerMessage = {
  id?: number;
  results?: FaqSearchHit[];
  size?: number;
  type: "READY" | "RESULTS";
};

export function useFaqSearch(catalog: FaqCatalog) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FaqSearchHit[]>([]);
  const [indexReady, setIndexReady] = useState(false);
  const [workerBacked, setWorkerBacked] = useState(false);
  const workerRef = useRef<Worker | null>(null);
  const requestRef = useRef(0);

  useEffect(() => {
    setIndexReady(false);
    setWorkerBacked(false);
    if (typeof Worker === "undefined") {
      setIndexReady(true);
      return;
    }
    let worker: Worker | null = null;
    try {
      worker = new Worker(
        new URL("../../workers/faqSearch.worker.ts", import.meta.url),
      );
      workerRef.current = worker;
      setWorkerBacked(true);
      worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
        const message = event.data;
        if (message.type === "READY") {
          setIndexReady(true);
          return;
        }
        if (
          message.type === "RESULTS" &&
          message.id === requestRef.current
        ) {
          setResults(message.results || []);
        }
      };
      worker.onerror = () => {
        worker?.terminate();
        workerRef.current = null;
        setWorkerBacked(false);
        setIndexReady(true);
      };
      worker.postMessage({ catalog, type: "INIT" });
    } catch {
      workerRef.current = null;
      setWorkerBacked(false);
      setIndexReady(true);
    }
    return () => {
      worker?.terminate();
      workerRef.current = null;
    };
  }, [catalog]);

  const fallbackResults = useMemo(() => {
    if (!query.trim()) return [];
    return searchFaq(catalog, query).slice(0, FAQ_SEARCH_RESULT_LIMIT);
  }, [catalog, query]);

  useEffect(() => {
    const clean = query.trim();
    if (!clean) {
      setResults([]);
      return;
    }
    const worker = workerRef.current;
    if (!worker || !indexReady) {
      setResults(fallbackResults);
      return;
    }
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    const timer = window.setTimeout(() => {
      worker.postMessage({
        id: requestId,
        query: clean,
        type: "SEARCH",
      });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [fallbackResults, indexReady, query]);

  return {
    clearQuery: () => setQuery(""),
    hasQuery: Boolean(query.trim()),
    indexReady,
    query,
    results,
    setQuery,
    workerBacked,
  };
}
