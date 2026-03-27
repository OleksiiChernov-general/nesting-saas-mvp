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
        <div className="rounded-2xl bg-slate-100 px-4 py-4 text-sm text-slate-600">
          Run a successful nesting job to see yield, scrap, and sheet usage metrics.
        </div>
      </Panel>
    );
  }

  const placedParts = result?.parts_placed ?? result?.layouts.reduce((sum, layout) => sum + layout.placements.length, 0) ?? 0;
  const layoutCount = result?.layouts_used ?? result?.layouts.length ?? 0;
  const yieldValue = result?.yield_ratio ?? result?.yield ?? result?.yield_value ?? 0;
  const scrapPercent = result?.scrap_ratio ?? (result?.total_sheet_area ? result.scrap_area / result.total_sheet_area : 0);

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
      <div className="grid grid-cols-2 gap-3">
        {metrics.map((metric) => (
          <div className="rounded-2xl bg-slate-100 px-4 py-4" key={metric.label}>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{metric.label}</div>
            <div className="mt-2 text-lg font-semibold text-slate-900">{metric.value}</div>
          </div>
        ))}
      </div>

      {result?.part_summaries && result.part_summaries.length > 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
          <div className="text-sm font-semibold text-slate-900 mb-3">Per-Part Results</div>
          <div className="space-y-3">
            {result.part_summaries.map((part) => (
              <div key={part.part_id} className="rounded-lg border border-slate-200 bg-white px-3 py-3">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{part.filename || part.part_id}</div>
                    <div className="text-xs text-slate-500">ID: {part.part_id}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-slate-900">{part.placed_quantity}</div>
                    <div className="text-xs text-slate-500">placed</div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {part.requested_quantity !== null ? (
                    <div className="text-slate-600">
                      Requested: <span className="font-semibold">{part.requested_quantity}</span>
                    </div>
                  ) : null}
                  {part.remaining_quantity !== null ? (
                    <div className={part.remaining_quantity > 0 ? "text-amber-600" : "text-emerald-600"}>
                      Remaining: <span className="font-semibold">{part.remaining_quantity}</span>
                    </div>
                  ) : null}
                  <div className="text-slate-600">
                    Area: <span className="font-semibold">{formatNumber(part.area_contribution)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {result?.unplaced_parts.length ? (
        <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">
          <div className="font-semibold mb-1">Unplaced parts:</div>
          {result.unplaced_parts.join(", ")}
        </div>
      ) : null}

      {result?.warnings?.length ? (
        <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">
          <div className="font-semibold mb-1">Warnings:</div>
          {result.warnings.join(" ")}
        </div>
      ) : null}
    </Panel>
  );
}
