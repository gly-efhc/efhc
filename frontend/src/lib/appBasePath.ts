/** The deployment prefix is supplied by the same generated Next config as basePath. */
export function appBasePath(): string {
  if (process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1") return "";
  const base = process.env.NEXT_PUBLIC_EFHC_BASE_PATH || "";
  if (!base) return "";
  if (!/^\/[A-Za-z0-9_.-]+$/.test(base) || base === "/." || base === "/..") {
    throw new Error("Invalid configured Pages basePath");
  }
  return base;
}

/** router.push takes logical paths; old session stacks may contain deployment prefixes. */
export function withoutAppBasePath(path: string): string {
  const base = appBasePath();
  if (!base) return path;
  // Test-3 is retained solely for migration of history saved before the repository rename.
  const prefixes = [...new Set([base, "/Test-3"])];
  let result = path;
  for (;;) {
    const prefix = prefixes.find(p => result === p || result.startsWith(p + "/") || result.startsWith(p + "?"));
    if (!prefix) return result;
    result = result.slice(prefix.length) || "/";
  }
}
