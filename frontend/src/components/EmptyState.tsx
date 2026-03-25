type EmptyStateProps = {
  onBrowseClick: () => void;
};

export function EmptyState({ onBrowseClick }: EmptyStateProps) {
  return (
    <div className="flex h-full min-h-[540px] flex-col items-center justify-center rounded-[2rem] border border-dashed border-slate-300 bg-white/70 px-8 text-center shadow-panel">
      <p className="rounded-full bg-accent/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-accent">
        Fast Workflow
      </p>
      <h2 className="mt-6 max-w-xl text-4xl font-semibold tracking-tight text-ink">Nesting SaaS MVP</h2>
      <p className="mt-4 max-w-lg text-sm leading-7 text-slate-600">
        Upload a DXF, validate geometry, run nesting, and inspect material usage in a single view.
      </p>
      <button
        className="mt-8 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-steel"
        onClick={onBrowseClick}
        type="button"
      >
        Select DXF File(s)
      </button>
    </div>
  );
}
