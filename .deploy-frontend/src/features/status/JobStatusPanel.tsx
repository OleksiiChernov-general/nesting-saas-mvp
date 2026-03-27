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
  RUNNING: "bg-amber-100 text-amber-700",
  SUCCEEDED: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-rose-100 text-rose-700",
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
      <div className="rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-600">
        {disconnected
          ? "Backend unavailable. Check the API server and VITE_API_BASE_URL."
          : polling
            ? "Polling backend every 1.5s..."
            : job?.state === "SUCCEEDED"
              ? "Job completed successfully."
              : job?.state === "FAILED"
                ? "Job failed. Fix inputs and run again."
                : "Polling idle"}
      </div>
      {job?.error ? <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{job.error}</div> : null}
      {error ? <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}
    </Panel>
  );
}
