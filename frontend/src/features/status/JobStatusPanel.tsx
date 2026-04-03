import type { JobResponse } from "../../types/api";
import { Panel } from "../../components/Panel";
import type { Translate } from "../../i18n";

type JobStatusPanelProps = {
  job: JobResponse | null;
  polling: boolean;
  error: string | null;
  disconnected: boolean;
  t: Translate;
};

const stateTone: Record<string, string> = {
  CREATED: "bg-slate-800 text-slate-200",
  QUEUED: "bg-sky-500/15 text-sky-300",
  RUNNING: "bg-amber-500/15 text-amber-300",
  PARTIAL: "bg-amber-500/15 text-amber-300",
  SUCCEEDED: "bg-emerald-500/15 text-emerald-300",
  FAILED: "bg-rose-500/15 text-rose-300",
  CANCELLED: "bg-slate-700 text-slate-300",
};

export function JobStatusPanel({ job, polling, error, disconnected, t }: JobStatusPanelProps) {
  const statusLabel = disconnected ? t("job.disconnected") : job ? t(`job.state.${job.state}`) : t("job.state.IDLE");
  const tone = disconnected ? "bg-rose-500/15 text-rose-300" : job ? stateTone[job.state] : "bg-slate-800 text-slate-300";

  return (
    <Panel title={t("job.title")} subtitle={t("job.subtitle")}>
      <div className="flex items-center justify-between rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3">
        <span className="text-sm text-slate-400">{t("job.currentState")}</span>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>
          {statusLabel}
        </span>
      </div>
      {job ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.02] px-4 py-3">
          <div className="mb-2 flex items-center justify-between text-sm text-slate-400">
            <span>{t("job.progress")}</span>
            <span>{Math.round((job.progress ?? 0) * 100)}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-800">
            <div className="h-2 rounded-full bg-[linear-gradient(135deg,var(--brand-primary)_0%,var(--brand-accent)_100%)] transition-all" style={{ width: `${Math.max(4, Math.round((job.progress ?? 0) * 100))}%` }} />
          </div>
        </div>
      ) : null}
      <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.02] px-4 py-3 text-sm text-slate-400">
        {disconnected
          ? t("job.backendUnavailable")
          : job?.status_message
            ? job.status_message
            : polling
              ? t("job.polling")
            : job?.state === "SUCCEEDED"
              ? t("job.completed")
              : job?.state === "FAILED"
                ? t("job.failed")
                : t("job.idle")}
      </div>
      {job?.mode || job?.summary ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            {job.mode ? <span>{t("screen3.mode")}: <strong>{job.mode === "fill_sheet" ? t("nesting.fillSheet") : t("nesting.batchQuantity")}</strong></span> : null}
            {job.summary ? <span>{t("job.partsInJob")}: <strong>{job.summary.total_parts}</strong></span> : null}
            {typeof job.run_number === "number" ? <span>{t("screen3.runNumber")}: <strong>{job.run_number}</strong></span> : null}
            {typeof job.compute_time_sec === "number" && job.compute_time_sec > 0 ? <span>{t("screen3.computeTime")}: <strong>{job.compute_time_sec.toFixed(2)}s</strong></span> : null}
            {typeof job.current_yield === "number" && job.current_yield > 0 ? <span>{t("metrics.yield")}: <strong>{(job.current_yield * 100).toFixed(2)}%</strong></span> : null}
          </div>
        </div>
      ) : null}
      {typeof job?.improvement_percent === "number" && job.improvement_percent !== 0 ? (
        <div className={`rounded-2xl border px-4 py-3 text-sm ${job.improvement_percent > 0 ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border-[color:var(--border)] bg-black/15 text-slate-300"}`}>
          {t("job.improvedBy", { value: job.improvement_percent.toFixed(2) })}
        </div>
      ) : null}
      {job?.artifact_url ? (
        <a
          className="block rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-center text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110"
          href={job.artifact_url}
          rel="noreferrer"
          target="_blank"
        >
          {t("job.downloadJson")}
        </a>
      ) : null}
      {job?.error ? <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{job.error}</div> : null}
      {error ? <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
    </Panel>
  );
}
