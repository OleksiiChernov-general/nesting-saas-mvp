type SheetNavigatorProps = {
  current: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
};

export function SheetNavigator({ current, total, onPrevious, onNext }: SheetNavigatorProps) {
  return (
    <div className="flex items-center gap-2">
      <button
        className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300"
        disabled={current <= 0}
        onClick={onPrevious}
        type="button"
      >
        Prev
      </button>
      <span className="text-sm text-slate-500">
        Sheet {total === 0 ? 0 : current + 1} / {total}
      </span>
      <button
        className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300"
        disabled={current >= total - 1}
        onClick={onNext}
        type="button"
      >
        Next
      </button>
    </div>
  );
}
