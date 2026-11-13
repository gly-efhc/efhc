import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../../public/" + "FRONTEND_" + "v" + "866.css", import.meta.url), "utf8");
const picker = readFileSync(new URL("../../src/components/profile/CompactLanguagePicker.tsx", import.meta.url), "utf8");

test("profile general button theme excludes both approved language picker implementations", () => {
  const selector = css.match(/\.source-profile-settings-card button(?<excluded>(?::not\([^)]+\))+),/);
  assert.ok(selector, "The original profile theme rule remains present");
  for (const className of [
    "source-profile-language-button",
    "source-profile-language-option",
    "efhc-compact-language-picker_button",
    "efhc-compact-language-picker_option",
  ]) {
    assert.ok(selector.groups.excluded.includes(":not(." + className + ")"), className);
  }
  assert.match(picker, /className="efhc-compact-language-picker_button"/);
  assert.match(picker, /className="efhc-compact-language-picker_option"/);
  assert.match(css.slice(css.indexOf(selector[0]), css.indexOf(selector[0]) + 500),
    /background-color:rgba\(var\(--efhc-ct-accent-rgb\),\.055\)!important/,
    "Other profile buttons retain the color theme rule");
});
