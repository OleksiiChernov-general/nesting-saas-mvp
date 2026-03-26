import { Field } from "../../components/Field";
import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";

export type NestingFormState = {
  sheetWidth: string;
  sheetHeight: string;
  sheetQuantity: string;
  gap: string;
  objective: "MAX_YIELD" | "MIN_SHEETS";
  debug: boolean;
};

type NestingFormPanelProps = {
  form: NestingFormState;
  errors: Partial<Record<keyof NestingFormState, string>>;
  loading: boolean;
  cleanupReady: boolean;
  statusMessage: string;
  scaleWarning: string | null;
  scaleWarningAcknowledged: boolean;
  onChange: <K extends keyof NestingFormState>(field: K, value: NestingFormState[K]) => void;
  onScaleWarningAcknowledged: (acknowledged: boolean) => void;
  onSubmit: () => void;
};

const inputClassName =
  "w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-accent";

export function NestingFormPanel({
  form,
  errors,
  loading,
  cleanupReady,
  statusMessage,
  scaleWarning,
  scaleWarningAcknowledged,
  onChange,
  onScaleWarningAcknowledged,
  onSubmit,
}: NestingFormPanelProps) {
  return (
    <Panel title="Nesting Job" subtitle="Define the sheet stock and optimization target.">
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
          <option value="MAX_YIELD">MAX_YIELD</option>
          <option value="MIN_SHEETS">MIN_SHEETS</option>
        </select>
      </Field>
      <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
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
        className="w-full rounded-2xl bg-accent px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        disabled={!cleanupReady || loading || Object.values(errors).some(Boolean) || Boolean(scaleWarning && !scaleWarningAcknowledged)}
        onClick={onSubmit}
        type="button"
      >
        {loading ? "Creating Job..." : "Run Nesting"}
      </button>
      <StatusMessage message={statusMessage} tone={cleanupReady ? "neutral" : "warning"} />
      {!cleanupReady ? (
        <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">
          Cleanup must succeed before nesting can start.
        </div>
      ) : null}
    </Panel>
  );
}
