import { LogoSVG } from "../components/LogoSVG";

type HomeLanguage = "en" | "tr" | "uk";

type HomePageProps = {
  language: HomeLanguage;
  onLanguageChange: (language: HomeLanguage) => void;
  onUploadClick: () => void;
  onWorkspaceClick: () => void;
};

const homeCopy: Record<HomeLanguage, { badge: string; title: string; description: string; upload: string; workspace: string }> = {
  en: {
    badge: "Production Nesting Platform",
    title: "Nestora",
    description: "Upload DXF parts, prepare geometry, and move into the production workspace for bounded nesting runs and result review.",
    upload: "Upload DXF",
    workspace: "Go to Workspace",
  },
  tr: {
    badge: "Uretim Yerlesim Platformu",
    title: "Nestora",
    description: "DXF parcalarini yukleyin, geometriyi hazirlayin ve sinirli nesting calismalari ile sonuc incelemesi icin calisma alanina gecin.",
    upload: "DXF Yukle",
    workspace: "Calisma Alanina Git",
  },
  uk: {
    badge: "\u041f\u043b\u0430\u0442\u0444\u043e\u0440\u043c\u0430 \u0432\u0438\u0440\u043e\u0431\u043d\u0438\u0447\u043e\u0433\u043e \u0440\u043e\u0437\u043a\u0440\u043e\u044e",
    title: "Nestora",
    description:
      "\u0417\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0443\u0439\u0442\u0435 DXF-\u0434\u0435\u0442\u0430\u043b\u0456, \u0433\u043e\u0442\u0443\u0439\u0442\u0435 \u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0456\u044e \u0442\u0430 \u043f\u0435\u0440\u0435\u0445\u043e\u0434\u044c\u0442\u0435 \u0432 \u0440\u043e\u0431\u043e\u0447\u0438\u0439 \u043f\u0440\u043e\u0441\u0442\u0456\u0440 \u0434\u043b\u044f \u043e\u0431\u043c\u0435\u0436\u0435\u043d\u0438\u0445 \u0440\u043e\u0437\u0440\u0430\u0445\u0443\u043d\u043a\u0456\u0432 \u0456 \u043f\u0435\u0440\u0435\u0433\u043b\u044f\u0434\u0443 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0456\u0432.",
    upload: "\u0417\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438 DXF",
    workspace: "\u041f\u0435\u0440\u0435\u0439\u0442\u0438 \u0432 Workspace",
  },
};

export function HomePage({ language, onLanguageChange, onUploadClick, onWorkspaceClick }: HomePageProps) {
  const copy = homeCopy[language];

  return (
    <div className="min-h-screen px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <section className="overflow-hidden rounded-[2.5rem] border border-[color:var(--border)] bg-[linear-gradient(145deg,rgba(17,24,39,0.96)_0%,rgba(10,12,16,0.98)_55%,rgba(16,185,129,0.09)_100%)] shadow-panel">
          <div className="grid gap-10 px-6 py-8 lg:grid-cols-[minmax(0,1.2fr)_340px] lg:px-10 lg:py-12">
            <div className="flex min-h-[420px] flex-col justify-between">
              <div>
                <div className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-300">
                  {copy.badge}
                </div>
                <div className="mt-8">
                  <LogoSVG className="flex flex-col items-start gap-5" iconClassName="h-36 w-36 shrink-0 md:h-40 md:w-40" wordmarkClassName="min-w-0" />
                </div>
                <h1 className="mt-8 text-4xl font-semibold tracking-tight text-white md:text-6xl">{copy.title}</h1>
                <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300 md:text-lg">{copy.description}</p>
              </div>

              <div className="mt-10 flex flex-wrap gap-4">
                <button
                  className="rounded-full bg-[linear-gradient(135deg,#1dd197_0%,#10b981_58%,#0f9f73_100%)] px-8 py-4 text-sm font-semibold text-white shadow-[0_18px_40px_rgba(16,185,129,0.25)] transition hover:brightness-105"
                  onClick={onUploadClick}
                  type="button"
                >
                  {copy.upload}
                </button>
                <button
                  className="rounded-full border border-[color:var(--border)] bg-white/5 px-8 py-4 text-sm font-semibold text-slate-100 transition hover:border-accent hover:text-white"
                  onClick={onWorkspaceClick}
                  type="button"
                >
                  {copy.workspace}
                </button>
              </div>
            </div>

            <aside className="rounded-[2rem] border border-[color:var(--border)] bg-black/20 p-6">
              <div className="text-sm font-semibold text-slate-100">Language</div>
              <select
                aria-label="Language"
                className="mt-4 w-full rounded-2xl border border-[color:var(--border)] bg-[color:var(--card-bg)] px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-emerald-400"
                onChange={(event) => onLanguageChange(event.target.value as HomeLanguage)}
                value={language}
              >
                <option value="en">English</option>
                <option value="tr">T\u00fcrk\u00e7e</option>
                <option value="uk">\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430</option>
              </select>

              <div className="mt-8 rounded-[1.5rem] border border-[color:var(--border)] bg-white/[0.03] p-5">
                <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Pages</div>
                <div className="mt-4 space-y-3 text-sm text-slate-300">
                  <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3">Home</div>
                  <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3">Workspace</div>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </div>
    </div>
  );
}
