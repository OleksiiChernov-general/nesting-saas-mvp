import type { NestingResultResponse } from "../../types/api";
import { Panel } from "../../components/Panel";
import { formatNumber, formatPercent } from "../../utils/numbers";
import type { Translate } from "../../i18n";

type MetricsPanelProps = {
  result: NestingResultResponse | null;
  t: Translate;
};

export function MetricsPanel({ result, t }: MetricsPanelProps) {
  if (!result) {
    return (
      <Panel title={t("metrics.title")} subtitle={t("metrics.subtitle")}>
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4 text-sm text-slate-400">
          {t("metrics.empty")}
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
  const economics = result.economics;
  const offcutSummary = result.offcut_summary;
  const reusableOffcuts = (result.offcuts ?? []).filter((piece) => piece.reusable);
  const leftoverSummaries = offcutSummary?.leftover_summaries ?? [];
  const batchOrders = result.batch?.orders ?? [];

  const metrics = [
    { label: t("metrics.yield"), value: formatPercent(yieldValue) },
    { label: t("metrics.scrap"), value: formatPercent(scrapPercent) },
    { label: t("metrics.partsPlaced"), value: `${placedParts}` },
    { label: t("metrics.layoutsUsed"), value: `${layoutCount}` },
    { label: t("metrics.usedArea"), value: formatNumber(result?.used_area ?? 0) },
    { label: t("metrics.scrapArea"), value: formatNumber(result?.scrap_area ?? 0) },
  ];

  return (
    <Panel title={t("metrics.title")} subtitle={t("metrics.subtitle")}>
      <div className="mb-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{t("metrics.nestingModeUsed")}</div>
          <div className="mt-1 text-base font-semibold text-slate-100">
            {result.mode === "fill_sheet" ? t("nesting.fillSheet") : t("nesting.batchQuantity")}
          </div>
        </div>
        <div className="rounded-2xl border border-sky-400/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
          <div className="text-xs uppercase tracking-[0.16em] text-sky-300">{t("metrics.multiPartJob")}</div>
          <div className="mt-1 text-base font-semibold">{t("metrics.activePartsInResult", { count: result.summary.total_parts })}</div>
          <div className="mt-1 text-xs text-sky-200">{t("metrics.perPartTracking")}</div>
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

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-sm font-semibold text-slate-100">{t("metrics.offcutSummary")}</div>
          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
            {offcutSummary?.approximation ? t("metrics.approximation") : t("metrics.exact")}
          </div>
        </div>
        {offcutSummary ? (
          <>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{t("metrics.usedArea")}</div>
                <div className="mt-1 text-base font-semibold text-slate-100">{formatNumber(result.used_area)}</div>
              </div>
              <div className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{t("metrics.totalLeftover")}</div>
                <div className="mt-1 text-base font-semibold text-slate-100">{formatNumber(offcutSummary.total_leftover_area)}</div>
              </div>
              <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 px-3 py-3 text-sm text-emerald-100">
                <div className="text-xs uppercase tracking-[0.16em] text-emerald-300">{t("metrics.reusableLeftover")}</div>
                <div className="mt-1 text-base font-semibold">{formatNumber(offcutSummary.reusable_leftover_area)}</div>
              </div>
              <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-3 py-3 text-sm text-amber-100">
                <div className="text-xs uppercase tracking-[0.16em] text-amber-300">{t("metrics.estimatedScrap")}</div>
                <div className="mt-1 text-base font-semibold">{formatNumber(offcutSummary.estimated_scrap_area)}</div>
              </div>
            </div>
            <div className="mt-3 text-xs text-slate-400">{offcutSummary.message}</div>
            {reusableOffcuts.length > 0 ? (
              <div className="mt-4 space-y-2">
                {reusableOffcuts.slice(0, 4).map((piece, index) => (
                  <div key={`${piece.sheet_id}-${piece.instance}-${piece.source}-${index}`} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-100">
                          {t("metrics.layoutLabel", { sheetId: piece.sheet_id, instance: piece.instance })}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {t("metrics.approxDimensions", {
                            width: piece.bounds.width.toFixed(2),
                            height: piece.bounds.height.toFixed(2),
                            shape: piece.approx_shape,
                          })}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold text-emerald-200">{formatNumber(piece.area)}</div>
                        <div className="text-xs text-slate-500">{t("metrics.sourceSummary", { source: piece.source.split("_").join(" ") })}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : leftoverSummaries.length > 0 ? (
              <div className="mt-4 space-y-2">
                {leftoverSummaries.slice(0, 4).map((piece, index) => (
                  <div key={`${piece.sheet_id}-${piece.instance}-${piece.source ?? "summary"}-${index}`} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-100">
                          {t("metrics.layoutLabel", { sheetId: piece.sheet_id, instance: piece.instance })}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {t("metrics.approxDimensionsNoShape", {
                            width: piece.width.toFixed(2),
                            height: piece.height.toFixed(2),
                          })}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold text-emerald-200">{formatNumber(piece.area)}</div>
                        <div className="text-xs text-slate-500">{t("metrics.sourceSummary", { source: piece.source?.split("_").join(" ") ?? t("metrics.summarySource") })}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div className="text-sm text-slate-400">{t("metrics.empty")}</div>
        )}
      </div>

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4">
        <div className="mb-3">
          <div className="text-sm font-semibold text-slate-100">{t("metrics.economicsTitle")}</div>
          <div className="mt-1 text-xs text-slate-500">{t("metrics.economicsSubtitle")}</div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <EconomicsCard
            label={t("metrics.materialCost")}
            value={formatMoney(economics?.material_cost, economics?.currency, false, t)}
          />
          <EconomicsCard
            label={t("metrics.usedMaterialCost")}
            value={formatMoney(economics?.used_material_cost, economics?.currency, economics?.used_material_cost_estimated === true, t)}
          />
          <EconomicsCard
            label={t("metrics.wasteCost")}
            value={formatMoney(economics?.waste_cost, economics?.currency, economics?.waste_cost_estimated === true, t)}
          />
          <EconomicsCard
            label={t("metrics.savingsPercent")}
            value={formatPercentValue(economics?.savings_percent, economics?.savings_percent_estimated === true, t)}
          />
        </div>
        <div className="mt-3 text-xs text-slate-500">{economics?.message ?? t("metrics.notConfigured")}</div>
      </div>

      {placedPartTypes > 1 ? (
        <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
          <div className="font-semibold">{t("metrics.mixedSheetResult")}</div>
          <div className="mt-1 text-emerald-200">{t("metrics.mixedSheetResultSubtitle", { count: placedPartTypes })}</div>
        </div>
      ) : null}

      {result.mode === "fill_sheet" && placedParts > 1 ? (
        <div className="rounded-2xl border border-sky-400/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
          <div className="font-semibold">{t("metrics.repeatedFillResult")}</div>
          <div className="mt-1 text-sky-200">{t("metrics.repeatedFillResultSubtitle", { count: placedParts })}</div>
        </div>
      ) : null}

      {result.mode === "batch_quantity" && partialFitParts.length > 0 ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <div className="font-semibold">{t("metrics.partialFitBatchResult")}</div>
          <div className="mt-1 text-amber-200">{t("metrics.partialFitBatchResultSubtitle")}</div>
        </div>
      ) : null}

      {result.parts.length > 0 ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate-100">{t("metrics.perPartResults")}</div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{t("metrics.partEntries", { count: result.parts.length })}</div>
          </div>
          <div className="space-y-3">
            {result.parts.map((part) => (
              <div key={part.part_id} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-100">{part.filename || part.part_id}</div>
                    <div className="text-xs text-slate-500">{t("metrics.partId", { id: part.part_id })}</div>
                    <div className="text-xs text-slate-500">
                      {t("metrics.partMeta", {
                        order: part.order_name || part.order_id || t("metrics.unassigned"),
                        priority: part.priority ?? t("common.notSet"),
                      })}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-slate-100">{part.placed_quantity}</div>
                    <div className="text-xs text-slate-500">{t("metrics.placed")}</div>
                  </div>
                </div>
                <div className="grid gap-2 text-xs md:grid-cols-4">
                  <div className="rounded-lg border border-[color:var(--border)] bg-black/15 px-2 py-2 text-slate-300">
                    {t("metrics.requested")}: <span className="font-semibold">{part.requested_quantity}</span>
                  </div>
                  <div className="rounded-lg border border-[color:var(--border)] bg-black/15 px-2 py-2 text-slate-300">
                    {t("metrics.placed")}: <span className="font-semibold">{part.placed_quantity}</span>
                  </div>
                  <div className={`rounded-lg px-2 py-2 ${part.remaining_quantity > 0 ? "border border-amber-400/30 bg-amber-500/10 text-amber-200" : "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200"}`}>
                    {t("metrics.remaining")}: <span className="font-semibold">{part.remaining_quantity}</span>
                  </div>
                  <div className="text-slate-300">
                    {t("metrics.area")}: <span className="font-semibold">{formatNumber(part.area_contribution)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {batchOrders.length > 0 ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate-100">{t("metrics.batchOrders")}</div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{t("metrics.orderEntries", { count: batchOrders.length })}</div>
          </div>
          <div className="space-y-2">
            {batchOrders.map((order) => (
              <div key={order.order_id} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                <div className="font-semibold text-slate-100">{order.order_name || order.order_id}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {t("metrics.batchOrderMeta", {
                    id: order.order_id,
                    parts: order.part_ids?.join(", ") || t("metrics.notListed"),
                    priority: order.priority ?? t("common.notSet"),
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {result?.unplaced_parts.length ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <div className="font-semibold mb-1">{t("metrics.partsDidNotFullyFit")}</div>
          {result.unplaced_parts.join(", ")}
        </div>
      ) : null}

      {result?.warnings?.length ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <div className="font-semibold mb-1">{t("metrics.warningsTitle")}</div>
          {result.warnings.join(" ")}
        </div>
      ) : null}

      {result.optimization_history && result.optimization_history.length > 0 ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate-100">{t("metrics.optimizationHistory")}</div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{t("metrics.runsCount", { count: result.optimization_history.length })}</div>
          </div>
          <div className="space-y-2">
            {result.optimization_history.slice().reverse().map((entry) => (
              <div key={entry.job_id} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                {t("metrics.historyEntry", {
                  run: entry.run_number,
                  yield: formatPercent(entry.yield),
                  seconds: formatNumber(entry.compute_time_sec),
                  improvement: entry.improvement_percent.toFixed(2),
                })}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

function formatMoney(value: number | null | undefined, currency: string | null | undefined, estimated: boolean, t: Translate): string {
  if (typeof value !== "number") return t("metrics.notAvailable");
  const suffix = currency ? ` ${currency}` : "";
  const estimate = estimated ? ` (${t("metrics.estimated")})` : "";
  return `${value.toFixed(2)}${suffix}${estimate}`;
}

function formatPercentValue(value: number | null | undefined, estimated: boolean, t: Translate): string {
  if (typeof value !== "number") return t("metrics.notAvailable");
  const estimate = estimated ? ` (${t("metrics.estimated")})` : "";
  return `${value.toFixed(1)}%${estimate}`;
}

function EconomicsCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</div>
      <div className="mt-1 text-base font-semibold text-slate-100">{value}</div>
    </div>
  );
}
