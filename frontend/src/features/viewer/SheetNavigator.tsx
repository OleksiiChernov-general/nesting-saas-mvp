import type { Translate } from "../../i18n";

type SheetNavigatorProps = {
  current: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
  t: Translate;
};

export function SheetNavigator({ current, total, onPrevious, onNext, t }: SheetNavigatorProps) {
  return (
    <div className="flex items-center gap-2">
      <button
        className="rounded-full border border-[color:var(--border)] bg-white/[0.03] px-3 py-1 text-sm text-slate-200 transition hover:border-accent hover:text-white disabled:cursor-not-allowed disabled:text-slate-500"
        disabled={current <= 0}
        onClick={onPrevious}
        type="button"
      >
        {t("viewer.prev")}
      </button>
      <span className="text-sm text-slate-400">
        {t("viewer.sheet", { current: total === 0 ? 0 : current + 1, total })}
      </span>
      <button
        className="rounded-full border border-[color:var(--border)] bg-white/[0.03] px-3 py-1 text-sm text-slate-200 transition hover:border-accent hover:text-white disabled:cursor-not-allowed disabled:text-slate-500"
        disabled={current >= total - 1}
        onClick={onNext}
        type="button"
      >
        {t("common.next")}
      </button>
    </div>
  );
}
