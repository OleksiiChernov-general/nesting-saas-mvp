import type { ChangeEvent, RefObject } from "react";

import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";
import type { Translate } from "../../i18n";

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
  orderId?: string;
  orderName?: string;
  priority?: string;
};

type UploadPanelProps = {
  files: UploadedFileItem[];
  loading: boolean;
  error: string | null;
  statusMessage: string;
  onFilesSelected: (files: File[]) => void;
  onPartMetaChange: (partId: string, patch: Partial<Pick<UploadedFileItem, "orderId" | "orderName" | "priority">>) => void;
  inputRef: RefObject<HTMLInputElement | null>;
  t: Translate;
};

export function UploadPanel({
  files,
  loading,
  error,
  statusMessage,
  onFilesSelected,
  onPartMetaChange,
  inputRef,
  t,
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
    <Panel title={t("upload.title")} subtitle={t("upload.subtitle")}>
      <input
        ref={inputRef}
        accept=".dxf"
        aria-label={t("upload.dxfFile")}
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
        {loading ? t("upload.uploading") : t("upload.select")}
      </button>
      <input
        readOnly
        value={
          files.length > 0
            ? t("upload.count", { count: files.length })
            : t("upload.noneSelected")
        }
        className="block w-full rounded-2xl border border-[color:var(--border)] bg-black/20 px-3 py-3 text-sm text-slate-300"
      />
      <StatusMessage message={statusMessage} tone={error ? "error" : files.some((file) => file.status === "parsed") ? "success" : "neutral"} />
      {files.length > 0 ? (
        <div className="space-y-3 rounded-[1.5rem] border border-[color:var(--border)] bg-black/15 px-4 py-4">
          <div className="text-sm font-semibold text-slate-100">{t("upload.uploadedFiles")}</div>
          {files.map((file) => (
            <div key={file.id} className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-100">{file.name}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    {t("upload.polygons")}: {file.polygons} | {t("upload.invalidShapes")}: {file.invalidShapes}
                  </div>
                  {file.detectedUnits ? (
                    <div className="mt-1 text-xs text-slate-400">{t("upload.detectedUnits")}: {file.detectedUnits}</div>
                  ) : null}
                  <div className="mt-3 grid gap-2 md:grid-cols-3">
                    <input
                      className="rounded-xl border border-[color:var(--border)] bg-black/15 px-3 py-2 text-xs text-slate-200"
                      onChange={(event) => onPartMetaChange(file.id, { orderId: event.target.value })}
                      placeholder={t("upload.orderId")}
                      type="text"
                      value={file.orderId ?? ""}
                    />
                    <input
                      className="rounded-xl border border-[color:var(--border)] bg-black/15 px-3 py-2 text-xs text-slate-200"
                      onChange={(event) => onPartMetaChange(file.id, { orderName: event.target.value })}
                      placeholder={t("upload.orderName")}
                      type="text"
                      value={file.orderName ?? ""}
                    />
                    <input
                      className="rounded-xl border border-[color:var(--border)] bg-black/15 px-3 py-2 text-xs text-slate-200"
                      min="1"
                      onChange={(event) => onPartMetaChange(file.id, { priority: event.target.value })}
                      placeholder={t("upload.priority")}
                      type="number"
                      value={file.priority ?? ""}
                    />
                  </div>
                  {file.auditWarning ? <div className="mt-2 text-xs text-amber-300">{file.auditWarning}</div> : null}
                  {file.error ? <div className="mt-2 text-xs text-rose-300">{file.error}</div> : null}
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusClassName[file.status]}`}>
                  {t(`upload.fileStatus.${file.status}`)}
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
