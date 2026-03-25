import type { ChangeEvent, RefObject } from "react";

import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";

type UploadPanelProps = {
  file: File | null;
  importedFileName: string | null;
  loading: boolean;
  error: string | null;
  statusMessage: string;
  onFileChange: (file: File | null) => void;
  inputRef: RefObject<HTMLInputElement | null>;
};

export function UploadPanel({
  file,
  importedFileName,
  loading,
  error,
  statusMessage,
  onFileChange,
  inputRef,
}: UploadPanelProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    onFileChange(event.target.files?.[0] ?? null);
  };

  return (
    <Panel title="Upload DXF" subtitle="Import a DXF file and extract closed polygons.">
      <input
        ref={inputRef}
        accept=".dxf"
        aria-label="DXF file"
        className="block w-full rounded-2xl border border-slate-300 bg-slate-50 px-3 py-3 text-sm text-slate-700 file:mr-4 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white"
        onChange={handleChange}
        type="file"
      />
      <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
        {file ? `Selected: ${file.name}` : "Select a DXF file to start upload automatically."}
      </div>
      <StatusMessage message={statusMessage} tone={error ? "error" : importedFileName ? "success" : "neutral"} />
      {importedFileName ? (
        <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">Imported: {importedFileName}</div>
      ) : null}
      {error ? <StatusMessage message={error} tone="error" /> : null}
    </Panel>
  );
}
