import type { Translate } from "../i18n";

type EmptyStateProps = {
  onBrowseClick: () => void;
  t: Translate;
};

export function EmptyState({ onBrowseClick, t }: EmptyStateProps) {
  return (
    <div className="flex h-full min-h-[560px] flex-col items-center justify-center rounded-[2.25rem] border border-dashed border-[color:var(--border)] bg-[linear-gradient(145deg,rgba(17,24,39,0.92)_0%,rgba(10,12,16,0.92)_100%)] px-8 text-center shadow-panel">
      <p className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-300">
        {t("empty.badge")}
      </p>
      <h2 className="mt-6 max-w-2xl text-4xl font-semibold tracking-tight text-ink md:text-5xl">{t("empty.title")}</h2>
      <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400 md:text-base">
        {t("empty.description")}
      </p>
      <button
        className="mt-8 rounded-full bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-7 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.28)] transition hover:brightness-110"
        onClick={onBrowseClick}
        type="button"
      >
        {t("upload.select")}
      </button>
    </div>
  );
}
