import en from "../translations/en.json";
import tr from "../translations/tr.json";
import uk from "../translations/uk.json";

export type AppLanguage = "en" | "tr" | "uk";

export const LANGUAGE_STORAGE_KEY = "nestora-language";

export const languageOptions: Array<{ value: AppLanguage; label: string }> = [
  { value: "en", label: "English" },
  { value: "tr", label: "Turkce" },
  { value: "uk", label: "Ukrainska" },
];

export type TranslationKey = string;
export type Translate = (key: TranslationKey, params?: Record<string, string | number>) => string;

export type TranslationDictionary = Record<string, string>;

const translations: Record<AppLanguage, TranslationDictionary> = { en, tr, uk };

// Translator notes for newly added keys:
// - `status.scaleWarningDetected` describes a likely DXF units mismatch. Keep the numeric placeholders unchanged.
// - `metrics.historyEntry` is one compact optimization-history line. Preserve `{run}`, `{yield}`, `{seconds}`, and `{improvement}`.
// - `metrics.partMeta`, `metrics.batchOrderMeta`, and related keys are concise UI summaries, not backend field names.

export function resolveLanguage(value: string | null | undefined): AppLanguage {
  return value === "tr" || value === "uk" ? value : "en";
}

export function readStoredLanguage(): AppLanguage {
  return resolveLanguage(window.localStorage.getItem(LANGUAGE_STORAGE_KEY));
}

export function writeStoredLanguage(language: AppLanguage): void {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
}

export function getTranslationDictionary(language: AppLanguage): TranslationDictionary {
  return translations[language];
}

export function getMissingTranslationKeys(language: AppLanguage): string[] {
  if (language === "en") return [];
  return Object.keys(translations.en).filter((key) => !(key in translations[language]));
}

export function translate(language: AppLanguage, key: TranslationKey, params?: Record<string, string | number>): string {
  const template = translations[language][key] ?? translations.en[key] ?? key;
  if (!params) return template;
  return Object.entries(params).reduce(
    (message, [paramKey, value]) => message.split(`{${paramKey}}`).join(String(value)),
    template,
  );
}
