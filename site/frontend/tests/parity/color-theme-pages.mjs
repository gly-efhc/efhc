import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const catalog = JSON.parse(readFileSync(new URL("../../src/design-system/color-theme-registry.json", import.meta.url), "utf8")).themes;
const routeSource = readFileSync(new URL("../../src/lib/themePageRegistry.ts", import.meta.url), "utf8");
const routeList = routeSource.match(/export const GLOBAL_THEME_PAGE_PATHS = Object\.freeze\(\[([\s\S]*?)\]\s+as const\)/)?.[1];
assert.ok(routeList, "Missing source USER route registry");
const routes = [...routeList.matchAll(/"([^"]+)"/g)].map((item) => item[1])
  .filter((path) => !["/browser-shop", "/404", "/500", "/_error"].includes(path));
const roles = [
  "canvas", "page", "chrome", "chrome-inset", "hero", "card", "inset",
  "active", "accent", "accent-soft", "accent-strong", "border",
  "border-strong", "text", "text-muted", "shadow", "glow", "focus",
];
// The frozen USER shell uses the active violet accent for glow after Theme03's
// historical vector is loaded. Compare with the accepted rendered Theme03,
// not the pre-shell JSON token; preserve the protected Theme03 appearance.
const theme03Roles = JSON.parse(readFileSync(new URL("../../src/design-system/theme03-chroma.json", import.meta.url), "utf8")).roles;
const theme03Expected = Object.fromEntries(
  ["accent", "accentStrong", "glow", "focus", "text", "textMuted", "border", "borderStrong"]
    .map(key => [key, key === "glow" ? theme03Roles.accent : theme03Roles[key]]),
);
const neutralRoles = ["canvas", "page", "chrome", "chrome-inset", "hero", "card", "inset", "text", "text-muted", "shadow"];
const layoutSelectors = [
  ".efhc-game-header", ".efhc-game-header_profile", ".efhc-game-header_balance",
  ".efhc-game-nav", ".efhc-game-nav_grid", ".efhc-game-hero",
  ".efhc-card", ".efhc-panel-tile", ".efhc-task-card", ".efhc-energy-stage",
  ".efhc-exchange-panel", ".efhc-hub-choice", ".efhc-faq-shell",
  ".efhc-profile-page", ".efhc-referrals-shell", ".efhc-ranks-shell",
  ".efhc-withdraw-shell",
].join(",");

export async function verifyColorThemePages(page, { base, artifacts }) {
  assert.equal(catalog.length, 10, "All ten color themes are required");
  assert.ok(routes.length >= 15, "USER route coverage shrank");
  const outcomes = [];
  const failures = [];
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    for (const route of routes) {
      const url = new URL(route.replace(/^\//, "") + (route === "/" ? "" : "/"), base).toString();
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 25000 });
      await page.locator('.efhc-independent-shell[data-interface-app-mode="user"]').first()
        .waitFor({ state: "attached", timeout: 12000 });
      const result = await page.evaluate(({ palette, roleNames, neutral, selectors, expectedTheme03 }) => {
        const root = document.documentElement;
        const shell = document.querySelector('.efhc-independent-shell[data-interface-app-mode="user"]');
        if (!shell) throw new Error("USER shell not mounted");
        const previous = [root, shell].map(node => ({
          node, color: node.getAttribute("data-color-theme-id"),
          legacy: node.getAttribute("data-global-theme-id"),
        }));
        const sample = [...shell.querySelectorAll(selectors)]
          .filter(node => {
            const rect = node.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          }).slice(0, 80);
        let expectedMaterial = null;
        let expectedRects = null;
        let expectedGeometry = null;
        const matrix = [];
        const mismatches = [];
        try {
          for (const entry of palette) {
            for (const node of [root, shell]) {
              node.setAttribute("data-color-theme-id", entry.id);
              node.setAttribute("data-global-theme-id", entry.id.slice(3));
            }
            const style = getComputedStyle(shell);
            const get = name => style.getPropertyValue(name).trim().replace(/\s+/g, "");
            const material = Object.fromEntries(neutral.map(name => [name, get("--efhc-color-" + name)]));
            const values = Object.fromEntries(roleNames.map(name => [name, get("--efhc-color-" + name)]));
            for (const [name, value] of Object.entries(values)) {
              if (!value) throw new Error("Unresolved role " + name + " / " + entry.id);
            }
            if (entry.id === "CT-03") {
              for (const [key, expected] of Object.entries(expectedTheme03)) {
                const role = key.replace(/[A-Z]/g, c => "-" + c.toLowerCase());
                const actual = get("--efhc-color-" + role).toLowerCase();
                const value = expected.toLowerCase().replace(/\s+/g, "");
                if (actual !== value) {
                  throw new Error("Theme03 qualified role differs at " + key + ": " + actual + " expected " + value);
                }
              }
            }
            if (get("--efhc-ct-accent").toLowerCase() !== entry.accent.toLowerCase()) {
              throw new Error("Wrong active accent " + entry.id + ": " + get("--efhc-ct-accent"));
            }
            if (!expectedMaterial) expectedMaterial = material;
            else for (const name of neutral) {
              if (material[name] !== expectedMaterial[name]) {
                throw new Error("Material role mismatch " + entry.id + "/" + name);
              }
            }
            if (get("--efhc-route-surface") !== material.page ||
                get("--efhc-route-surface-raised") !== material.hero) {
              throw new Error("Legacy route material overrides shared reference in " + entry.id);
            }
            const rects = sample.map(el => {
              const r = el.getBoundingClientRect();
              return [Math.round(r.width * 10) / 10, Math.round(r.height * 10) / 10];
            });
            const geometryProperties = [
              "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
              "borderTopLeftRadius", "borderTopRightRadius", "borderBottomRightRadius", "borderBottomLeftRadius",
              "fontSize", "lineHeight", "fontWeight", "paddingTop", "paddingRight",
              "paddingBottom", "paddingLeft", "columnGap", "rowGap", "display",
              "gridTemplateColumns", "boxSizing",
            ];
            const geometry = sample.map(el => {
              const computed = getComputedStyle(el);
              return Object.fromEntries(geometryProperties.map(property => [property, computed[property]]));
            });
            if (!expectedGeometry) expectedGeometry = geometry;
            else geometry.forEach((current, index) => {
              const previous = expectedGeometry[index];
              for (const property of geometryProperties) {
                if (current[property] !== previous[property] && mismatches.length < 40) {
                  mismatches.push({
                    color: entry.id,
                    element: String(sample[index]?.className || sample[index]?.tagName),
                    property,
                    baseline: previous[property],
                    actual: current[property],
                  });
                }
              }
            });
            if (!expectedRects) expectedRects = rects;
            else rects.forEach(([w, h], index) => {
              const [baseW, baseH] = expectedRects[index];
              if (Math.abs(w - baseW) > 1 || Math.abs(h - baseH) > 1) {
                if (mismatches.length < 40) mismatches.push({
                  color: entry.id,
                  element: String(sample[index]?.className || sample[index]?.tagName),
                  baseline: [baseW, baseH],
                  actual: [w, h],
                });
              }
            });
            matrix.push({ theme: entry.id, roles: roleNames.length, measuredElements: sample.length });
          }
        } finally {
          for (const {node,color,legacy} of previous) {
            if (color === null) node.removeAttribute("data-color-theme-id");
            else node.setAttribute("data-color-theme-id", color);
            if (legacy === null) node.removeAttribute("data-global-theme-id");
            else node.setAttribute("data-global-theme-id", legacy);
          }
        }
        return { matrix, mismatches };
      }, { palette: catalog, roleNames: roles, neutral: neutralRoles, selectors: layoutSelectors, expectedTheme03: theme03Expected });
      assert.equal(result.matrix.length, 10, "Missing theme on " + route + " at " + width);
      outcomes.push({ route, width, themes: result.matrix.length, measuredElements: result.matrix[0]?.measuredElements || 0 });
      for (const mismatch of result.mismatches) failures.push({ route, width, ...mismatch });
    }
  }
  if (artifacts) {
    const { writeFile } = await import("node:fs/promises");
    await writeFile(artifacts + "/color-theme-pages.json", JSON.stringify({ roles, outcomes, failures }, null, 2));
  }
  assert.equal(failures.length, 0, "Color-only geometry drift: " + JSON.stringify(failures.slice(0, 30)));
  return outcomes;
}
