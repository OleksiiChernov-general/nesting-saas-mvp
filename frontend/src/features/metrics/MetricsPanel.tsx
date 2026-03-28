import type { NestingResultResponse } from "../../types/api";
import { Panel } from "../../components/Panel";
import { formatNumber, formatPercent } from "../../utils/numbers";

type MetricsPanelProps = {
  result: NestingResultResponse | null;
};

export function MetricsPanel({ result }: MetricsPanelProps) {
  if (!result) {
    return (
      <Panel title="Result Metrics" subtitle="Material usage and placement output.">
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4 text-sm text-slate-400">
          Run a successful nesting job to see yield, scrap, and sheet usage metrics.
        </div>
      </Panel>
    );
  }

  const placedParts = result?.total_parts_placed ?? result?.parts_placed ?? result?.layouts.reduce((sum, layout) => sum + layout.placements.length, 0) ?? 0;
  const layoutCount = result?.layouts_used ?? result?.layouts.length ?? 0;
  const yieldValue = result?.yield_ratio ?? result?.yield ?? result?.yield_value ?? 0;
  const scrapPercent = result?.scrap_ratio ?? (result?.total_sheet_area ? result.scrap_area / result.total_sheet_area : 0);
  const placedPartTypes = result.parts.filter((part) => part.placed_quantity > 0).length;
  const partialFitParts = result.parts.filter((part) => part.remaining_quantity > 0);

  const metrics = [
    { label: "Yield", value: formatPercent(yieldValue) },
    { label: "Scrap", value: formatPercent(scrapPercent) },
    { label: "Parts placed", value: `${placedParts}` },
    { label: "Layouts used", value: `${layoutCount}` },
    { label: "Used area", value: formatNumber(result?.used_area ?? 0) },
    { label: "Scrap area", value: formatNumber(result?.scrap_area ?? 0) },
  ];

  return (
    <Panel title="Result Metrics" subtitle="Material usage and placement output.">
      <div className="mb-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Nesting Mode Used</div>
          <div className="mt-1 text-base font-semibold text-slate-100">
            {result.mode === "fill_sheet" ? "Fill Sheet" : "Batch Quantity"}
          </div>
        </div>
        <div className="rounded-2xl border border-sky-400/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
          <div className="text-xs uppercase tracking-[0.16em] text-sky-300">Multi-Part Job</div>
          <div className="mt-1 text-base font-semibold">Active parts in result: {result.summary.total_parts}</div>
          <div className="mt-1 text-xs text-sky-200">Per-part requested, placed, and remaining counts are tracked for the whole job.</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {metrics.map((metric) => (
          <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4" key={metric.label}>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{metric.label}</div>
            <div className="mt-2 text-lg font-semibold text-slate-100">{metric.value}</div>
          </div>
        ))}
      </div>

      {placedPartTypes > 1 ? (
        <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
          <div className="font-semibold">Mixed sheet result detected</div>
          <div className="mt-1 text-emerald-200">{placedPartTypes} part types were placed in this job result.</div>
        </div>
      ) : null}

      {result.mode === "fill_sheet" && placedParts > 1 ? (
        <div className="rounded-2xl border border-sky-400/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
          <div className="font-semibold">Repeated fill result confirmed</div>
          <div className="mt-1 text-sky-200">The backend kept placing parts until no enabled geometry could fit. Total placements: {placedParts}.</div>
        </div>
      ) : null}

      {result.mode === "batch_quantity" && partialFitParts.length > 0 ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <div className="font-semibold">Partial-fit batch result</div>
          <div className="mt-1 text-amber-200">Remaining quantities are explicit because the backend stopped only after no more requested parts could fit on the available sheets.</div>
        </div>
      ) : null}

      {result.parts.length > 0 ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate-100">Per-Part Results</div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{result.parts.length} part entries</div>
          </div>
          <div className="space-y-3">
            {result.parts.map((part) => (
              <div key={part.part_id} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-100">{part.filename || part.part_id}</div>
                    <div className="text-xs text-slate-500">ID: {part.part_id}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-slate-100">{part.placed_quantity}</div>
                    <div className="text-xs text-slate-500">placed</div>
                  </div>
                </div>
                <div className="grid gap-2 text-xs md:grid-cols-4">
                  <div className="rounded-lg border border-[color:var(--border)] bg-black/15 px-2 py-2 text-slate-300">
                    Requested: <span className="font-semibold">{part.requested_quantity}</span>
                  </div>
                  <div className="rounded-lg border border-[color:var(--border)] bg-black/15 px-2 py-2 text-slate-300">
                    Placed: <span className="font-semibold">{part.placed_quantity}</span>
                  </div>
                  <div className={`rounded-lg px-2 py-2 ${part.remaining_quantity > 0 ? "border border-amber-400/30 bg-amber-500/10 text-amber-200" : "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200"}`}>
                    Remaining: <span className="font-semibold">{part.remaining_quantity}</span>
                  </div>
                  <div className="text-slate-300">
                    Area: <span className="font-semibold">{formatNumber(part.area_contribution)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {result?.unplaced_parts.length ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <div className="font-semibold mb-1">Parts that did not fully fit:</div>
          {result.unplaced_parts.join(", ")}
        </div>
      ) : null}

      {result?.warnings?.length ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <div className="font-semibold mb-1">Warnings:</div>
          {result.warnings.join(" ")}
        </div>
      ) : null}
    </Panel>
  );
}
