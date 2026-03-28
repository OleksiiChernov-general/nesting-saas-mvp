import type { JobResponse } from "../../types/api";
import { Panel } from "../../components/Panel";

type JobStatusPanelProps = {
  job: JobResponse | null;
  polling: boolean;
  error: string | null;
  disconnected: boolean;
};

const stateTone: Record<string, string> = {
  CREATED: "bg-slate-800 text-slate-200",
  QUEUED: "bg-sky-500/15 text-sky-300",
  RUNNING: "bg-amber-500/15 text-amber-300",
  SUCCEEDED: "bg-emerald-500/15 text-emerald-300",
  FAILED: "bg-rose-500/15 text-rose-300",
  CANCELLED: "bg-slate-700 text-slate-300",
};

export function JobStatusPanel({ job, polling, error, disconnected }: JobStatusPanelProps) {
  const statusLabel = disconnected ? "Backend disconnected" : job?.state ?? "IDLE";
  const tone = disconnected ? "bg-rose-500/15 text-rose-300" : job ? stateTone[job.state] : "bg-slate-800 text-slate-300";

  return (
    <Panel title="Job Status" subtitle="Track the active nesting run.">
      <div className="flex items-center justify-between rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3">
        <span className="text-sm text-slate-400">Current state</span>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>
          {statusLabel}
        </span>
      </div>
      {job ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.02] px-4 py-3">
          <div className="mb-2 flex items-center justify-between text-sm text-slate-400">
            <span>Progress</span>
            <span>{Math.round((job.progress ?? 0) * 100)}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-800">
            <div className="h-2 rounded-full bg-[linear-gradient(135deg,var(--brand-primary)_0%,var(--brand-accent)_100%)] transition-all" style={{ width: `${Math.max(4, Math.round((job.progress ?? 0) * 100))}%` }} />
          </div>
        </div>
      ) : null}
      <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.02] px-4 py-3 text-sm text-slate-400">
        {disconnected
          ? "Backend unavailable. Check the API server and VITE_API_BASE_URL."
          : job?.status_message
            ? job.status_message
            : polling
              ? "Polling backend every 1.5s..."
            : job?.state === "SUCCEEDED"
              ? "Job completed successfully."
              : job?.state === "FAILED"
                ? "Job failed. Fix inputs and run again."
                : "Polling idle"}
      </div>
      {job?.mode || job?.summary ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            {job.mode ? <span>Mode: <strong>{job.mode === "fill_sheet" ? "Fill Sheet" : "Batch Quantity"}</strong></span> : null}
            {job.summary ? <span>Parts in job: <strong>{job.summary.total_parts}</strong></span> : null}
          </div>
        </div>
      ) : null}
      {job?.artifact_url ? (
        <a
          className="block rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-center text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110"
          href={job.artifact_url}
          rel="noreferrer"
          target="_blank"
        >
          Download JSON Result
        </a>
      ) : null}
      {job?.error ? <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{job.error}</div> : null}
      {error ? <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
    </Panel>
  );
}
