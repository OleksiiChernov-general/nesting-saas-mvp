import type { JobResponse } from "../../types/api";
import { Panel } from "../../components/Panel";

type JobStatusPanelProps = {
  job: JobResponse | null;
  polling: boolean;
  error: string | null;
  disconnected: boolean;
};

const stateTone: Record<string, string> = {
  CREATED: "bg-slate-100 text-slate-700",
  QUEUED: "bg-sky-100 text-sky-700",
  RUNNING: "bg-amber-100 text-amber-700",
  SUCCEEDED: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-rose-100 text-rose-700",
  CANCELLED: "bg-slate-200 text-slate-600",
};

export function JobStatusPanel({ job, polling, error, disconnected }: JobStatusPanelProps) {
  const statusLabel = disconnected ? "Backend disconnected" : job?.state ?? "IDLE";
  const tone = disconnected ? "bg-rose-100 text-rose-700" : job ? stateTone[job.state] : "bg-slate-200 text-slate-500";

  return (
    <Panel title="Job Status" subtitle="Track the active nesting run.">
      <div className="flex items-center justify-between rounded-2xl bg-slate-100 px-4 py-3">
        <span className="text-sm text-slate-600">Current state</span>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>
          {statusLabel}
        </span>
      </div>
      {job ? (
        <div className="rounded-2xl border border-slate-200 px-4 py-3">
          <div className="mb-2 flex items-center justify-between text-sm text-slate-600">
            <span>Progress</span>
            <span>{Math.round((job.progress ?? 0) * 100)}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100">
            <div className="h-2 rounded-full bg-slate-900 transition-all" style={{ width: `${Math.max(4, Math.round((job.progress ?? 0) * 100))}%` }} />
          </div>
        </div>
      ) : null}
      <div className="rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-600">
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
      {job?.artifact_url ? (
        <a
          className="block rounded-2xl bg-slate-900 px-4 py-3 text-center text-sm font-semibold text-white"
          href={job.artifact_url}
          rel="noreferrer"
          target="_blank"
        >
          Download JSON Result
        </a>
      ) : null}
      {job?.error ? <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{job.error}</div> : null}
      {error ? <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}
    </Panel>
  );
}
