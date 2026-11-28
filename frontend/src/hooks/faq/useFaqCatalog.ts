import { publicAssetPath } from "../../lib/publicAssetPath";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { FaqCatalog } from "../../data/faq/types";
import type { Lang } from "../../lib/i18n";
import { emitRuntimeProgress } from "../../lib/runtimeProgress";
import { queryKeys } from "../../queries/queryKeys";
import initialCatalog from "../../../public/faq/en.json";

function isFaqCatalog(value: unknown): value is FaqCatalog {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<FaqCatalog>;
  return (
    typeof candidate.title === "string" &&
    Array.isArray(candidate.sections)
  );
}

async function readCatalog(
  response: Response,
  onProgress: (value: number) => void,
): Promise<FaqCatalog> {
  if (!response.ok) {
    throw new Error(`FAQ_HTTP_${response.status}`);
  }
  const total = Number(response.headers.get("content-length") || 0);
  if (!response.body || !total) {
    onProgress(90);
    const payload = await response.json();
    if (!isFaqCatalog(payload)) {
      throw new Error("FAQ_SCHEMA_INVALID");
    }
    return payload;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  while (true) {
    const result = await reader.read();
    if (result.done) break;
    chunks.push(result.value);
    received += result.value.byteLength;
    onProgress(
      Math.min(90, Math.round((received / total) * 90)),
    );
  }
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const payload = JSON.parse(new TextDecoder().decode(bytes));
  if (!isFaqCatalog(payload)) {
    throw new Error("FAQ_SCHEMA_INVALID");
  }
  return payload;
}

export function useFaqCatalog(lang: Lang) {
  const [progress, setProgress] = useState(0);
  const query = useQuery({
    gcTime: 14 * 24 * 60 * 60 * 1000,
    queryFn: async () => {
      setProgress(5);
      emitRuntimeProgress({ channel: "faq", value: 5 });
      let catalog: FaqCatalog;
      try {
        const response = await fetch(publicAssetPath(`/faq/${lang}.json`), {
          cache: "default",
        });
        catalog = await readCatalog(response, (value) => {
          setProgress(value);
          emitRuntimeProgress({ channel: "faq", value });
        });
      } catch {
        // Load the canonical fallback only when static /faq/*.json is
        // unavailable, keeping all language catalogs out of the initial bundle.
        const { getFaqCatalog } = await import("../../data/faq");
        catalog = getFaqCatalog(lang);
      }
      setProgress(100);
      emitRuntimeProgress({
        channel: "faq",
        complete: true,
        value: 100,
      });
      return catalog;
    },
    queryKey: queryKeys.publicStatic.faq(lang),
    staleTime: Number.POSITIVE_INFINITY,
  });

  useEffect(() => {
    if (query.data) setProgress(100);
  }, [query.data]);

  return {
    // The checked-in English release catalog renders identically in SSR and
    // the first client frame. Locale/cache refresh may replace data afterward.
    catalog: query.data || initialCatalog as FaqCatalog,
    error: query.error instanceof Error
      ? query.error.message
      : null,
    loading: query.isLoading,
    progress,
  };
}
