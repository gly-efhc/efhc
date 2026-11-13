import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const picker = readFileSync(new URL("../../src/components/profile/CompactLanguagePicker.tsx", import.meta.url), "utf8");
const webProfile = readFileSync(new URL("../../src/features/profile/WebProfilePage.tsx", import.meta.url), "utf8");
const modal = readFileSync(new URL("../../src/components/ProfileModal.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../public/" + "FRONTEND_" + "v" + "866.css", import.meta.url), "utf8");

test("profile language picker receives the historical theme exclusions without changing frozen CSS", () => {
  const genericRule = css.match(/\.source-profile-settings-card button(?<excluded>(?::not\([^)]+\))+),/);
  assert.ok(genericRule, "The frozen profile button theme rule remains present");
  for (const oldName of ["source-profile-language-button", "source-profile-language-option"]) {
    assert.ok(genericRule.groups.excluded.includes(":not(." + oldName + ")"), oldName);
    assert.ok(picker.includes(oldName), oldName + " must be used by the React profile");
  }
  for (const newName of [
    "efhc-compact-language-picker_button",
    "efhc-compact-language-picker_menu",
    "efhc-compact-language-picker_option",
  ]) {
    assert.ok(picker.includes(newName), "Existing React class must be preserved: " + newName);
  }
  assert.match(picker, /profileSurface\?: boolean/);
  assert.match(picker, /source-profile-language-menu/);
  assert.match(webProfile, /<CompactLanguagePicker\s+profileSurface\s+value=/);
  assert.match(modal, /<CompactLanguagePicker\s+profileSurface\s+value=/);
  assert.match(picker, /props\.profileSurface \?/, "Shared component must leave Shop unmodified by default");
});
