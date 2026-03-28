import type { ChangeEvent, RefObject } from "react";

import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";

export type UploadedFileStatus = "selected" | "uploading" | "uploaded" | "parsed" | "failed";

export type UploadedFileItem = {
  id: string;
  name: string;
  status: UploadedFileStatus;
  polygons: number;
  invalidShapes: number;
  error: string | null;
  detectedUnits?: string | null;
  auditWarning?: string | null;
};

type UploadPanelProps = {
  files: UploadedFileItem[];
  loading: boolean;
  error: string | null;
  statusMessage: string;
  onFilesSelected: (files: File[]) => void;
  inputRef: RefObject<HTMLInputElement | null>;
};

export function UploadPanel({
  files,
  loading,
  error,
  statusMessage,
  onFilesSelected,
  inputRef,
}: UploadPanelProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    onFilesSelected(nextFiles);
    event.target.value = "";
  };

  const statusClassName: Record<UploadedFileStatus, string> = {
    selected: "bg-slate-800 text-slate-200",
    uploading: "bg-sky-500/15 text-sky-300",
    uploaded: "bg-indigo-500/15 text-indigo-300",
    parsed: "bg-emerald-500/15 text-emerald-300",
    failed: "bg-rose-500/15 text-rose-300",
  };

  return (
    <Panel title="Upload DXF" subtitle="Import one or more DXF files and extract closed polygons for the current nesting job.">
      <input
        ref={inputRef}
        accept=".dxf"
        aria-label="DXF file"
        className="hidden"
        multiple
        onChange={handleChange}
        type="file"
      />
      <button
        className="w-full rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:shadow-none"
        disabled={loading}
        onClick={() => inputRef.current?.click()}
        type="button"
      >
        {loading ? "Uploading DXF files..." : "Select DXF File(s)"}
      </button>
      <input
        readOnly
        value={
          files.length > 0
            ? `${files.length} file(s) in the upload list`
            : "No DXF files selected yet"
        }
        className="block w-full rounded-2xl border border-[color:var(--border)] bg-black/20 px-3 py-3 text-sm text-slate-300"
      />
      <StatusMessage message={statusMessage} tone={error ? "error" : files.some((file) => file.status === "parsed") ? "success" : "neutral"} />
      {files.length > 0 ? (
        <div className="space-y-3 rounded-[1.5rem] border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="text-sm font-semibold text-slate-100">Uploaded files</div>
          {files.map((file) => (
            <div key={file.id} className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-100">{file.name}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    Polygons: {file.polygons} | Invalid shapes: {file.invalidShapes}
                  </div>
                  {file.detectedUnits ? (
                    <div className="mt-1 text-xs text-slate-400">Detected units: {file.detectedUnits}</div>
                  ) : null}
                  {file.auditWarning ? <div className="mt-2 text-xs text-amber-300">{file.auditWarning}</div> : null}
                  {file.error ? <div className="mt-2 text-xs text-rose-300">{file.error}</div> : null}
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusClassName[file.status]}`}>
                  {file.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {error ? <StatusMessage message={error} tone="error" /> : null}
    </Panel>
  );
}
