import { describe, expect, it, beforeEach } from "vitest";

import { LANGUAGE_STORAGE_KEY, readStoredLanguage, translate, writeStoredLanguage } from "./index";

describe("i18n helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("persists selected language", () => {
    writeStoredLanguage("tr");
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("tr");
    expect(readStoredLanguage()).toBe("tr");
  });

  it("falls back to English when a key is missing in the selected language", () => {
    expect(translate("tr", "status.fallbackProbe")).toBe("English fallback probe");
  });

  it("falls back to English for unknown stored values", () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "de");
    expect(readStoredLanguage()).toBe("en");
  });
});
