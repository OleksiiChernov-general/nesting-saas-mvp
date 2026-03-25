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
    selected: "bg-slate-100 text-slate-700",
    uploading: "bg-sky-50 text-sky-700",
    uploaded: "bg-indigo-50 text-indigo-700",
    parsed: "bg-emerald-50 text-emerald-700",
    failed: "bg-rose-50 text-rose-700",
  };

  return (
    <Panel title="Upload DXF" subtitle="Import a DXF file and extract closed polygons.">
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
        className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
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
        className="block w-full rounded-2xl border border-slate-300 bg-slate-50 px-3 py-3 text-sm text-slate-700"
      />
      <StatusMessage message={statusMessage} tone={error ? "error" : files.some((file) => file.status === "parsed") ? "success" : "neutral"} />
      {files.length > 0 ? (
        <div className="space-y-3 rounded-2xl bg-slate-50 px-4 py-4">
          <div className="text-sm font-semibold text-slate-900">Uploaded files</div>
          {files.map((file) => (
            <div key={file.id} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-900">{file.name}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    Polygons: {file.polygons} | Invalid shapes: {file.invalidShapes}
                  </div>
                  {file.error ? <div className="mt-2 text-xs text-rose-700">{file.error}</div> : null}
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
