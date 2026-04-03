import { Field } from "../../components/Field";
import { OrderGroupingPanel } from "../../components/OrderEditor/OrderGroupingPanel";
import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";
import type { Translate } from "../../i18n";
import type { MaterialRecord } from "../../types/api";

export type NestingFormState = {
  selectedMaterialId: string;
  materialName: string;
  thickness: string;
  costPerSheet: string;
  currency: string;
  materialNotes: string;
  batchId: string;
  batchName: string;
  nestingMode: "fill_sheet" | "batch_quantity";
  sheetWidth: string;
  sheetHeight: string;
  sheetQuantity: string;
  sheetUnits: "mm" | "in";
  gap: string;
  rotationStep: string;
  objective: "MAX_YIELD" | "MIN_SHEETS";
  debug: boolean;
};

export type NestingPartDraft = {
  id: string;
  filename: string;
  parsedPolygonCount: number;
  cleanedPolygonCount: number;
  units: string | null;
  quantity: string;
  enabled: boolean;
  fillOnly: boolean;
  orderId: string;
  orderName: string;
  priority: string;
  hasGeometry: boolean;
  cleanupIssue: string | null;
};

type NestingFormPanelProps = {
  form: NestingFormState;
  parts: NestingPartDraft[];
  errors: Partial<Record<keyof NestingFormState | "parts", string>>;
  loading: boolean;
  cleanupReady: boolean;
  statusMessage: string;
  materials: MaterialRecord[];
  materialsLoading: boolean;
  materialsStatus: string;
  groupedOrders: Array<{ orderId: string; orderName: string; priority: string; partCount: number }>;
  scaleWarning: string | null;
  scaleWarningAcknowledged: boolean;
  onChange: <K extends keyof NestingFormState>(field: K, value: NestingFormState[K]) => void;
  onCreateMaterial: () => void;
  onPartChange: (partId: string, patch: Partial<Pick<NestingPartDraft, "quantity" | "enabled" | "fillOnly" | "orderId" | "orderName" | "priority">>) => void;
  onRemovePart: (partId: string) => void;
  onScaleWarningAcknowledged: (acknowledged: boolean) => void;
  onSubmit: () => void;
  onUpdateMaterial: () => void;
  submitLabel?: string;
  t: Translate;
};

const inputClassName =
  "w-full rounded-2xl border border-[color:var(--border)] bg-black/20 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-accent";

export function NestingFormPanel({
  form,
  parts,
  errors,
  loading,
  cleanupReady,
  statusMessage,
  materials,
  materialsLoading,
  materialsStatus,
  groupedOrders,
  scaleWarning,
  scaleWarningAcknowledged,
  onChange,
  onCreateMaterial,
  onPartChange,
  onRemovePart,
  onScaleWarningAcknowledged,
  onSubmit,
  onUpdateMaterial,
  submitLabel,
  t,
}: NestingFormPanelProps) {
  return (
    <Panel title={t("nesting.title")} subtitle={t("nesting.subtitle")}>
      <Field label={t("nesting.materialPreset")}>
        <select className={inputClassName} onChange={(event) => onChange("selectedMaterialId", event.target.value)} value={form.selectedMaterialId}>
          <option value="">{t("nesting.manualEntry")}</option>
          {materials.map((material) => (
            <option key={material.material_id} value={material.material_id}>
              {material.name}
            </option>
          ))}
        </select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <button
          className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent disabled:cursor-not-allowed disabled:opacity-60"
          disabled={materialsLoading}
          onClick={onCreateMaterial}
          type="button"
        >
          {t("nesting.saveMaterial")}
        </button>
        <button
          className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!form.selectedMaterialId || materialsLoading}
          onClick={onUpdateMaterial}
          type="button"
        >
          {t("nesting.updateMaterial")}
        </button>
      </div>
      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {materialsLoading ? t("nesting.loadingMaterials") : materialsStatus || t("nesting.materialHint")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field error={errors.materialName} label={t("nesting.materialName")}>
          <input className={inputClassName} onChange={(event) => onChange("materialName", event.target.value)} type="text" value={form.materialName} />
        </Field>
        <Field error={errors.thickness} label={t("nesting.thickness")}>
          <input className={inputClassName} min="0" onChange={(event) => onChange("thickness", event.target.value)} type="number" value={form.thickness} />
        </Field>
        <Field label={t("nesting.costPerSheet")}>
          <input className={inputClassName} min="0" onChange={(event) => onChange("costPerSheet", event.target.value)} type="number" value={form.costPerSheet} />
        </Field>
        <Field label={t("nesting.currency")}>
          <input className={inputClassName} onChange={(event) => onChange("currency", event.target.value)} type="text" value={form.currency} />
        </Field>
      </div>

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {t("nesting.productionIntent")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("nesting.batchId")}>
          <input className={inputClassName} onChange={(event) => onChange("batchId", event.target.value)} type="text" value={form.batchId} />
        </Field>
        <Field label={t("nesting.batchName")}>
          <input className={inputClassName} onChange={(event) => onChange("batchName", event.target.value)} type="text" value={form.batchName} />
        </Field>
      </div>
      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {groupedOrders.length > 0
          ? t("nesting.groupedOrdersIncluded", { count: groupedOrders.length })
          : t("nesting.defaultBatchGrouping")}
      </div>
      <Field label={t("nesting.nestingMode")}>
        <div className="flex gap-3">
          <button
            className={`flex-1 rounded-2xl border-2 px-4 py-3 text-sm font-semibold transition ${
              form.nestingMode === "fill_sheet"
                ? "border-accent bg-accent text-white"
                : "border-[color:var(--border)] bg-white/[0.03] text-slate-100 hover:border-accent"
            }`}
            onClick={() => onChange("nestingMode", "fill_sheet")}
            type="button"
          >
            {t("nesting.fillSheet")}
          </button>
          <button
            className={`flex-1 rounded-2xl border-2 px-4 py-3 text-sm font-semibold transition ${
              form.nestingMode === "batch_quantity"
                ? "border-accent bg-accent text-white"
                : "border-[color:var(--border)] bg-white/[0.03] text-slate-100 hover:border-accent"
            }`}
            onClick={() => onChange("nestingMode", "batch_quantity")}
            type="button"
          >
            {t("nesting.batchQuantity")}
          </button>
        </div>
      </Field>

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {form.nestingMode === "fill_sheet" ? (
          <div>
            <strong>{t("nesting.fillSheet")}:</strong> {t("nesting.fillSheetHelp")}
          </div>
        ) : (
          <div>
            <strong>{t("nesting.batchQuantity")}:</strong> {t("nesting.batchQuantityHelp")}
          </div>
        )}
      </div>

      <OrderGroupingPanel parts={parts} onPartChange={onPartChange} t={t} />

      <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-black/15 px-4 py-4">
        <div className="mb-3 text-sm font-semibold text-slate-100">{t("nesting.configureParts")}</div>
        {parts.length === 0 ? (
          <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm text-slate-400">{t("nesting.uploadFilesFirst")}</div>
        ) : (
          <div className="space-y-3">
            {parts.map((part) => (
              <div key={part.id} className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-100">{part.filename}</div>
                    <div className="mt-1 text-xs text-slate-400">
                      {t("nesting.parsedPolygons")}: {part.parsedPolygonCount} | {t("nesting.cleanedPolygons")}: {part.cleanedPolygonCount} | {t("nesting.units")}: {part.units ?? t("nesting.unknownUnits")}
                    </div>
                    <div className={`mt-2 text-xs ${part.hasGeometry ? "text-emerald-300" : "text-amber-300"}`}>
                      {part.hasGeometry ? t("nesting.readyForNesting") : part.cleanupIssue ?? t("nesting.noValidPolygon")}
                    </div>
                  </div>
                  <button
                    className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs font-semibold text-slate-300 hover:border-rose-400 hover:text-rose-300"
                    onClick={() => onRemovePart(part.id)}
                    type="button"
                  >
                    {t("common.remove")}
                  </button>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <label className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
                    <input
                      checked={part.enabled}
                      onChange={(event) => onPartChange(part.id, { enabled: event.target.checked })}
                      type="checkbox"
                    />
                    {t("nesting.includeInNesting")}
                  </label>

                  {form.nestingMode === "batch_quantity" ? (
                  <Field label={t("nesting.requestedQuantity")}>
                      <input
                        className={inputClassName}
                        min="1"
                        onChange={(event) => onPartChange(part.id, { quantity: event.target.value })}
                        type="number"
                        value={part.quantity}
                      />
                    </Field>
                  ) : (
                    <label className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
                      <input
                        checked={part.fillOnly}
                        onChange={(event) => onPartChange(part.id, { fillOnly: event.target.checked })}
                        type="checkbox"
                      />
                      {t("nesting.fillOnly")}
                    </label>
                  )}
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <Field label={t("upload.orderId")}>
                    <input
                      className={inputClassName}
                      onChange={(event) => onPartChange(part.id, { orderId: event.target.value })}
                      type="text"
                      value={part.orderId}
                    />
                  </Field>
                  <Field label={t("upload.orderName")}>
                    <input
                      className={inputClassName}
                      onChange={(event) => onPartChange(part.id, { orderName: event.target.value })}
                      type="text"
                      value={part.orderName}
                    />
                  </Field>
                  <Field label={t("upload.priority")}>
                    <input
                      className={inputClassName}
                      min="1"
                      onChange={(event) => onPartChange(part.id, { priority: event.target.value })}
                      type="number"
                      value={part.priority}
                    />
                  </Field>
                </div>
              </div>
            ))}
          </div>
        )}
        {errors.parts ? <div className="mt-3 text-xs text-rose-300">{errors.parts}</div> : null}
      </div>

      {groupedOrders.length > 0 ? (
        <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="mb-3 text-sm font-semibold text-slate-100">{t("nesting.batchGrouping")}</div>
          <div className="space-y-2">
            {groupedOrders.map((order) => (
              <div key={order.orderId} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                <div className="font-semibold text-slate-100">{order.orderName || order.orderId}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {t("common.id")}: {order.orderId} | {t("metrics.parts")}: {order.partCount} | {t("upload.priority")}: {order.priority || t("common.notSet")}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {t("nesting.enterSheetParameters")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field error={errors.sheetWidth} label={t("nesting.sheetWidth")}>
          <input className={inputClassName} min="0" onChange={(event) => onChange("sheetWidth", event.target.value)} type="number" value={form.sheetWidth} />
        </Field>
        <Field error={errors.sheetHeight} label={t("nesting.sheetHeight")}>
          <input className={inputClassName} min="0" onChange={(event) => onChange("sheetHeight", event.target.value)} type="number" value={form.sheetHeight} />
        </Field>
        <Field error={errors.sheetQuantity} label={t("nesting.sheetQuantity")}>
          <input className={inputClassName} min="1" onChange={(event) => onChange("sheetQuantity", event.target.value)} type="number" value={form.sheetQuantity} />
        </Field>
        <Field label={t("nesting.sheetUnits")}>
          <select className={inputClassName} onChange={(event) => onChange("sheetUnits", event.target.value as NestingFormState["sheetUnits"])} value={form.sheetUnits}>
            <option value="mm">mm</option>
            <option value="in">in</option>
          </select>
        </Field>
        <Field error={errors.gap} label={t("nesting.gap")}>
          <input className={inputClassName} min="0" onChange={(event) => onChange("gap", event.target.value)} type="number" value={form.gap} />
        </Field>
        <Field error={errors.rotationStep} label={t("nesting.rotationStep")}>
          <select className={inputClassName} onChange={(event) => onChange("rotationStep", event.target.value)} value={form.rotationStep}>
            <option value="45">{t("nesting.rotationOptionDegrees", { value: 45 })}</option>
            <option value="90">{t("nesting.rotationOptionDegrees", { value: 90 })}</option>
            <option value="180">{t("nesting.rotationOptionDegrees", { value: 180 })}</option>
            <option value="360">{t("nesting.rotationOptionNone")}</option>
          </select>
        </Field>
      </div>
      <Field label={t("nesting.materialNotes")}>
        <textarea
          className={`${inputClassName} min-h-24 resize-y`}
          onChange={(event) => onChange("materialNotes", event.target.value)}
          value={form.materialNotes}
        />
      </Field>
      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {t("nesting.backendPayloadHint")}
      </div>
      <Field label={t("nesting.objective")}>
        <select
          className={inputClassName}
          onChange={(event) => onChange("objective", event.target.value as NestingFormState["objective"])}
          value={form.objective}
        >
          <option value="MAX_YIELD">{t("nesting.maxYield")}</option>
          <option value="MIN_SHEETS">{t("nesting.minSheets")}</option>
        </select>
      </Field>
      <label className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
        <input checked={form.debug} onChange={(event) => onChange("debug", event.target.checked)} type="checkbox" />
        {t("nesting.debug")}
      </label>
      {scaleWarning ? (
        <div className="space-y-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <div className="font-semibold">{t("nesting.scaleTitle")}</div>
          <div>{scaleWarning}</div>
          <label className="flex items-center gap-3">
            <input
              checked={scaleWarningAcknowledged}
              onChange={(event) => onScaleWarningAcknowledged(event.target.checked)}
              type="checkbox"
            />
            {t("nesting.scaleAcknowledge")}
          </label>
        </div>
      ) : null}
      <button
        className="w-full rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:shadow-none"
        disabled={!cleanupReady || loading || Object.values(errors).some(Boolean) || Boolean(scaleWarning && !scaleWarningAcknowledged)}
        onClick={onSubmit}
        type="button"
      >
        {loading ? t("screen3.creatingJob") : submitLabel ?? t("screen3.runNesting")}
      </button>
      <StatusMessage message={statusMessage} tone={cleanupReady ? "neutral" : "warning"} />
      {!cleanupReady ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {t("nesting.cleanupRequired")}
        </div>
      ) : null}
    </Panel>
  );
}
