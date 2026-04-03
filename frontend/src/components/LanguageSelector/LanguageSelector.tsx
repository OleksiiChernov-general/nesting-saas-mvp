import { languageOptions, type AppLanguage, type Translate } from "../../i18n";

type LanguageSelectorProps = {
  language: AppLanguage;
  onLanguageChange: (language: AppLanguage) => void;
  t: Translate;
  className?: string;
};

export function LanguageSelector({ language, onLanguageChange, t, className }: LanguageSelectorProps) {
  return (
    <select
      aria-label={t("common.language")}
      className={className ?? "w-full rounded-2xl border border-[color:var(--border)] bg-[color:var(--card-bg)] px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-emerald-400"}
      onChange={(event) => onLanguageChange(event.target.value as AppLanguage)}
      value={language}
    >
      {languageOptions.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
