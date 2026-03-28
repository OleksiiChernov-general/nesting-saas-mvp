import { Field } from "../../components/Field";
import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";

export type NestingFormState = {
  nestingMode: "fill_sheet" | "batch_quantity";
  sheetWidth: string;
  sheetHeight: string;
  sheetQuantity: string;
  sheetUnits: "mm" | "in";
  gap: string;
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
  scaleWarning: string | null;
  scaleWarningAcknowledged: boolean;
  onChange: <K extends keyof NestingFormState>(field: K, value: NestingFormState[K]) => void;
  onPartChange: (partId: string, patch: Partial<Pick<NestingPartDraft, "quantity" | "enabled" | "fillOnly">>) => void;
  onRemovePart: (partId: string) => void;
  onScaleWarningAcknowledged: (acknowledged: boolean) => void;
  onSubmit: () => void;
  submitLabel?: string;
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
  scaleWarning,
  scaleWarningAcknowledged,
  onChange,
  onPartChange,
  onRemovePart,
  onScaleWarningAcknowledged,
  onSubmit,
  submitLabel = "Run Nesting",
}: NestingFormPanelProps) {
  return (
    <Panel title="Production Nesting" subtitle="Build a real nesting job with one or more parts, a clear production mode, and explicit quantities.">
      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        Step 3: Select the production intent for this job.
      </div>
      <Field label="Nesting Mode">
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
            Fill Sheet
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
            Batch Quantity
          </button>
        </div>
      </Field>

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        {form.nestingMode === "fill_sheet" ? (
          <div>
            <strong>Fill Sheet:</strong> keep placing enabled parts until no more geometry fits. Mark a part as <strong>Fill only</strong> to exclude the others from this fill run.
          </div>
        ) : (
          <div>
            <strong>Batch Quantity:</strong> each enabled part must have a requested quantity. The result will report placed and remaining counts per part.
          </div>
        )}
      </div>

      <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-black/15 px-4 py-4">
        <div className="mb-3 text-sm font-semibold text-slate-100">Step 4: Configure uploaded parts</div>
        {parts.length === 0 ? (
          <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm text-slate-400">Upload DXF files first to build the part list.</div>
        ) : (
          <div className="space-y-3">
            {parts.map((part) => (
              <div key={part.id} className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-100">{part.filename}</div>
                    <div className="mt-1 text-xs text-slate-400">
                      Parsed polygons: {part.parsedPolygonCount} | Cleaned polygons: {part.cleanedPolygonCount} | Units: {part.units ?? "unknown"}
                    </div>
                    <div className={`mt-2 text-xs ${part.hasGeometry ? "text-emerald-300" : "text-amber-300"}`}>
                      {part.hasGeometry ? "Ready for nesting" : part.cleanupIssue ?? "No valid polygon is available for nesting."}
                    </div>
                  </div>
                  <button
                    className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs font-semibold text-slate-300 hover:border-rose-400 hover:text-rose-300"
                    onClick={() => onRemovePart(part.id)}
                    type="button"
                  >
                    Remove
                  </button>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <label className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
                    <input
                      checked={part.enabled}
                      onChange={(event) => onPartChange(part.id, { enabled: event.target.checked })}
                      type="checkbox"
                    />
                    Include in nesting
                  </label>

                  {form.nestingMode === "batch_quantity" ? (
                    <Field label="Requested quantity">
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
                      Fill with this part only
                    </label>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {errors.parts ? <div className="mt-3 text-xs text-rose-300">{errors.parts}</div> : null}
      </div>

      <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-xs text-slate-400">
        Step 5: Enter sheet size and nesting parameters.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field error={errors.sheetWidth} label="Sheet width">
          <input className={inputClassName} min="0" onChange={(event) => onChange("sheetWidth", event.target.value)} type="number" value={form.sheetWidth} />
        </Field>
        <Field error={errors.sheetHeight} label="Sheet height">
          <input className={inputClassName} min="0" onChange={(event) => onChange("sheetHeight", event.target.value)} type="number" value={form.sheetHeight} />
        </Field>
        <Field error={errors.sheetQuantity} label="Sheet quantity">
          <input className={inputClassName} min="1" onChange={(event) => onChange("sheetQuantity", event.target.value)} type="number" value={form.sheetQuantity} />
        </Field>
        <Field label="Sheet units">
          <select className={inputClassName} onChange={(event) => onChange("sheetUnits", event.target.value as NestingFormState["sheetUnits"])} value={form.sheetUnits}>
            <option value="mm">mm</option>
            <option value="in">in</option>
          </select>
        </Field>
        <Field error={errors.gap} label="Gap">
          <input className={inputClassName} min="0" onChange={(event) => onChange("gap", event.target.value)} type="number" value={form.gap} />
        </Field>
      </div>
      <Field label="Objective">
        <select
          className={inputClassName}
          onChange={(event) => onChange("objective", event.target.value as NestingFormState["objective"])}
          value={form.objective}
        >
          <option value="MAX_YIELD">Maximize Yield</option>
          <option value="MIN_SHEETS">Minimize Sheets</option>
        </select>
      </Field>
      <label className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
        <input checked={form.debug} onChange={(event) => onChange("debug", event.target.checked)} type="checkbox" />
        Return geometry debug payload and bbox overlays
      </label>
      {scaleWarning ? (
        <div className="space-y-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <div className="font-semibold">Possible Units / Scale Mismatch</div>
          <div>{scaleWarning}</div>
          <label className="flex items-center gap-3">
            <input
              checked={scaleWarningAcknowledged}
              onChange={(event) => onScaleWarningAcknowledged(event.target.checked)}
              type="checkbox"
            />
            I understand the scale warning and still want to run nesting
          </label>
        </div>
      ) : null}
      <button
        className="w-full rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:shadow-none"
        disabled={!cleanupReady || loading || Object.values(errors).some(Boolean) || Boolean(scaleWarning && !scaleWarningAcknowledged)}
        onClick={onSubmit}
        type="button"
      >
        {loading ? "Creating Job..." : submitLabel}
      </button>
      <StatusMessage message={statusMessage} tone={cleanupReady ? "neutral" : "warning"} />
      {!cleanupReady ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Cleanup must produce at least one enabled part with valid geometry before nesting can start.
        </div>
      ) : null}
    </Panel>
  );
}
