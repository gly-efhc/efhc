/** EFHC Pages real compressed-route budget check for a compiled Next.js .next tree.
 * Public import excludes private release_config and historical reports; budgets
 * use the exact route thresholds and compression algorithms of scripts/budgets.mjs.
 * No fallback or mock file is accepted when the Next build is absent.
 */
import { readFileSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { gzipSync, brotliCompressSync, constants } from "node:zlib";
import { dirname, join, resolve } from "node:path";
const root = process.cwd();
const next = join(root, ".next");
const manifest = JSON.parse(readFileSync(join(next, "build-manifest.json"), "utf8"));
const limits = (route) => route === "/faq"
  ? { gzip: 300_000, brotli: 250_000 }
  : route.startsWith("/admin")
    ? { gzip: 420_000, brotli: 350_000 }
    : { gzip: 420_000, brotli: 370_000 };
const rows = [];
for (const [route, assets] of Object.entries(manifest.pages || {})) {
  const files = [...new Set(assets)].filter((f) => f.endsWith(".js") || f.endsWith(".css"));
  let raw = 0, gzip = 0, brotli = 0;
  for (const file of files) {
    const pathname = join(next, file);
    const payload = readFileSync(pathname);
    raw += statSync(pathname).size;
    gzip += gzipSync(payload, { level: 9 }).length;
    brotli += brotliCompressSync(payload, {
      params: { [constants.BROTLI_PARAM_QUALITY]: 5 },
    }).length;
  }
  const budget = limits(route);
  rows.push({
    route, assets: files.length, raw_bytes: raw, gzip_bytes: gzip,
    brotli_bytes: brotli, gzip_budget: budget.gzip,
    brotli_budget: budget.brotli,
    status: gzip <= budget.gzip && brotli <= budget.brotli ? "PASS" : "FAIL",
  });
}
rows.sort((a, b) => a.route.localeCompare(b.route));
const failed = rows.filter((row) => row.status === "FAIL");
const out = resolve(process.env.EFHC_BUDGET_OUTPUT || join(root, "pages-budget-evidence.json"));
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify({
  schema: "EFHC_PAGES_REAL_COMPRESSED_ROUTE_BUDGETS_V1",
  status: failed.length ? "FAILED" : "PASSED", routes: rows.length,
  baseline_comparison: "NOT_AVAILABLE_IN_PUBLIC_PAGES_RUNNER",
  failed_routes: failed.map((row) => row.route), rows,
}, null, 2) + "\n");
console.log(`EFHC COMPRESSED ROUTE BUDGETS: ${failed.length ? "FAIL" : "PASS"}; ` +
            `routes=${rows.length}; failed=${failed.length}; baseline=NOT_AVAILABLE`);
for (const row of failed) {
  console.error(`FAIL route=${row.route} gzip=${row.gzip_bytes}/${row.gzip_budget} ` +
                `brotli=${row.brotli_bytes}/${row.brotli_budget}; assets=${row.assets}`);
}
if (failed.length) process.exitCode = 1;
