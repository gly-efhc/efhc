export function searchNorm(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ё/g, "е")
    .replace(/[^\p{L}\p{N}\s]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function excerpt(text: string, query: string): string {
  const clean = text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/^[-*•]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!clean) return "";
  const q = searchNorm(query);
  if (!q) return clean;
  const base = searchNorm(clean);
  const pos = base.indexOf(q);
  if (pos < 0) return clean;
  const start = Math.max(0, pos - 56);
  const end = Math.min(clean.length, pos + q.length + 84);
  const part = clean.slice(start, end).trim();
  const pre = start > 0 ? "…" : "";
  const post = end < clean.length ? "…" : "";
  return `${pre}${part}${post}`;
}
