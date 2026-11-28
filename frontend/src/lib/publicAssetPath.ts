import {appBasePath} from "./appBasePath";
/** Resolve checked-in public assets under the exact GitHub Pages repository
 * basePath. Production Next.js remains rooted at /; no runtime proxy or
 * artificial read-only restriction is introduced. */
export function publicAssetPath(path: `/${string}`): string {
  if (typeof window === "undefined") return path;
  const base = appBasePath();
  // Static export rewriting may already have prefixed a literal asset path.
  if (base && (path === base || path.startsWith(base + "/"))) return path;
  return `${base}${path}`;
}
