import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";

const root = process.cwd();
const manifestPath = resolve(root, "release-assets-manifest.json");
const faqLanguages = [
  "ru", "en", "uk", "de", "fr", "es", "it",
  "tr", "pl", "da", "hi", "id", "sw", "pt", "ko", "ja",
];
const localeLanguages = [...faqLanguages];
const requiredFaqAssets = [...faqLanguages.map(lang => `public/faq/${lang}.json`), "src/data/faq/catalogs.ts"];

function fail(message) {
  console.error(`EFHC RELEASE ASSETS VERIFY: FAIL; ${message}`);
  process.exit(1);
}

function checksum(path) {
  return createHash("sha256")
    .update(readFileSync(path))
    .digest("hex");
}

if (!existsSync(manifestPath)) {
  fail("release-assets-manifest.json is missing");
}

let manifest;
try {
  manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
} catch (error) {
  fail(`invalid release asset manifest: ${error}`);
}
if (manifest.schema !== "efhc.frontend.faq-assets") {
  fail("unsupported release asset manifest schema");
}
if (!manifest.files || typeof manifest.files !== "object") {
  fail("manifest files map is missing");
}
if (manifest.asset_state !== "CHECKED_IN_BEFORE_RELEASE_PACKAGING") {
  fail("frontend assets are not marked checked-in");
}
if (manifest.packaging_mutates_runtime_assets !== false) {
  fail("release packaging must not mutate runtime assets");
}
if (
  !Array.isArray(manifest.packaging_generation_dependencies) ||
  manifest.packaging_generation_dependencies.length !== 0
) {
  fail("release packaging generation dependency forbidden");
}
if (manifest.ssot_role !== "DUPLICATE_CONTROL_ONLY_NO_RUNTIME_WRITE") {
  fail("FAQ SSOT must be duplicate control only");
}
if (manifest.packaging_source !== "checked-in production frontend assets") {
  fail("release packaging source must be checked-in assets");
}

if (Object.keys(manifest.files).length !== requiredFaqAssets.length ||
    requiredFaqAssets.some(path => !Object.hasOwn(manifest.files, path))) {
  fail("approved FAQ asset scope mismatch");
}

for (const [relativePath, expected] of Object.entries(manifest.files)) {
  const absolutePath = resolve(root, relativePath);
  if (absolutePath !== root && !absolutePath.startsWith(root + sep)) {
    fail(`unsafe asset path: ${relativePath}`);
  }
  if (!existsSync(absolutePath) || !statSync(absolutePath).isFile()) {
    fail(`missing packaged asset: ${relativePath}`);
  }
  const expectedHash = Array.isArray(expected)
    ? expected.join("")
    : expected;
  const actual = checksum(absolutePath);
  if (actual !== expectedHash) {
    fail(`checksum mismatch: ${relativePath}`);
  }
  if (relativePath.endsWith(".json")) {
    try {
      JSON.parse(readFileSync(absolutePath, "utf8"));
    } catch (error) {
      fail(`invalid JSON asset ${relativePath}: ${error}`);
    }
  }
}

const russian = JSON.parse(readFileSync(resolve(root, "public/locale/ru.json"), "utf8"));
const userKeys = Object.keys(russian).filter(key => !key.startsWith("admin."));
for (const language of localeLanguages) {
  const locale = JSON.parse(readFileSync(resolve(root, "public", "locale", language + ".json"), "utf8"));
  for (const key of userKeys) {
    if (!Object.hasOwn(locale, key) || typeof locale[key] !== "string" ||
        (russian[key].trim() && !locale[key].trim())) {
      fail("incomplete locale " + language + ": " + key);
    }
  }
}

console.log("EFHC RELEASE ASSETS VERIFY: PASS; approved FAQ assets=" +
  requiredFaqAssets.length + "; user locale keys=" + userKeys.length +
  "; languages=" + localeLanguages.length);
