import { LogoSVG } from "../components/LogoSVG";
import { LanguageSelector } from "../components/LanguageSelector";
import { type AppLanguage, type Translate } from "../i18n";

type HomePageProps = {
  language: AppLanguage;
  onLanguageChange: (language: AppLanguage) => void;
  onUploadClick: () => void;
  onWorkspaceClick: () => void;
  t: Translate;
};
export function HomePage({ language, onLanguageChange, onUploadClick, onWorkspaceClick, t }: HomePageProps) {

  return (
    <div className="min-h-screen px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <section className="overflow-hidden rounded-[2.5rem] border border-[color:var(--border)] bg-[linear-gradient(145deg,rgba(17,24,39,0.96)_0%,rgba(10,12,16,0.98)_55%,rgba(16,185,129,0.09)_100%)] shadow-panel">
          <div className="grid gap-10 px-6 py-8 lg:grid-cols-[minmax(0,1.2fr)_340px] lg:px-10 lg:py-12">
            <div className="flex min-h-[420px] flex-col justify-between">
              <div>
                <div className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-300">
                  {t("home.badge")}
                </div>
                <div className="mt-8">
                  <LogoSVG className="flex flex-col items-start gap-5" iconClassName="h-36 w-36 shrink-0 md:h-40 md:w-40" wordmarkClassName="min-w-0" />
                </div>
                <h1 className="mt-8 text-4xl font-semibold tracking-tight text-white md:text-6xl">Nestora</h1>
                <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300 md:text-lg">{t("home.description")}</p>
              </div>

              <div className="mt-10 flex flex-wrap gap-4">
                <button
                  className="rounded-full bg-[linear-gradient(135deg,#1dd197_0%,#10b981_58%,#0f9f73_100%)] px-8 py-4 text-sm font-semibold text-white shadow-[0_18px_40px_rgba(16,185,129,0.25)] transition hover:brightness-105"
                  onClick={onUploadClick}
                  type="button"
                >
                  {t("home.upload")}
                </button>
                <button
                  className="rounded-full border border-[color:var(--border)] bg-white/5 px-8 py-4 text-sm font-semibold text-slate-100 transition hover:border-accent hover:text-white"
                  onClick={onWorkspaceClick}
                  type="button"
                >
                  {t("home.workspace")}
                </button>
              </div>
            </div>

            <aside className="rounded-[2rem] border border-[color:var(--border)] bg-black/20 p-6">
              <div className="text-sm font-semibold text-slate-100">{t("common.language")}</div>
              <LanguageSelector
                className="mt-4 w-full rounded-2xl border border-[color:var(--border)] bg-[color:var(--card-bg)] px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-emerald-400"
                language={language}
                onLanguageChange={onLanguageChange}
                t={t}
              />

              <div className="mt-8 rounded-[1.5rem] border border-[color:var(--border)] bg-white/[0.03] p-5">
                <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{t("home.pages")}</div>
                <div className="mt-4 space-y-3 text-sm text-slate-300">
                  <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3">{t("home.pageHome")}</div>
                  <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3">{t("home.pageWorkspace")}</div>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </div>
    </div>
  );
}
