import type { RefObject } from "react";

import { ConnectionBadge } from "../components/ConnectionBadge";
import { EmptyState } from "../components/EmptyState";
import { LogoSVG } from "../components/LogoSVG";
import { StatusMessage } from "../components/StatusMessage";
import { MetricsPanel } from "../features/metrics/MetricsPanel";
import { type NestingFormState, NestingFormPanel } from "../features/nesting/NestingFormPanel";
import { JobStatusPanel } from "../features/status/JobStatusPanel";
import { CleanupPanel } from "../features/upload/CleanupPanel";
import { type UploadedFileItem, UploadPanel } from "../features/upload/UploadPanel";
import { LayoutViewer } from "../features/viewer/LayoutViewer";
import type { CleanGeometryResponse, ImportResponse, JobResponse, NestingResultResponse, PolygonPayload } from "../types/api";

type WorkspaceUploadItem = UploadedFileItem & {
  quantity: string;
  enabled: boolean;
  fillOnly: boolean;
  cleanedPolygons: PolygonPayload[];
  nestingPolygon: PolygonPayload | null;
  cleanupError: string | null;
  detectedUnits?: string | null;
  polygons?: number;
};

type WorkspacePageProps = {
  healthChecking: boolean;
  connected: boolean;
  resetWorkflow: () => void;
  uploadError: string | null;
  uploadedFiles: WorkspaceUploadItem[];
  fileInputRef: RefObject<HTMLInputElement | null>;
  uploading: boolean;
  handleFilesSelected: (files: FileList | null) => Promise<void>;
  uploadStatus: string;
  cleanupResult: CleanGeometryResponse | null;
  cleanupError: string | null;
  importResult: ImportResponse | null;
  cleanupLoading: boolean;
  handleClean: () => Promise<void>;
  cleanupStatus: string;
  cleanupReadyPartsCount: number;
  validationErrors: string[];
  form: NestingFormState;
  jobLoading: boolean;
  handleFormChange: (name: keyof NestingFormState, value: string | boolean) => void;
  handlePartChange: (partId: string, patch: Partial<Pick<WorkspaceUploadItem, "quantity" | "enabled" | "fillOnly">>) => void;
  handleRemovePart: (partId: string) => void;
  setScaleWarningAcknowledged: (value: boolean) => void;
  handleRunJob: () => Promise<void>;
  scaleWarning: string | null;
  scaleWarningAcknowledged: boolean;
  nestingStatus: string;
  result: NestingResultResponse | null;
  canShowResult: boolean;
  activeSheetIndex: number;
  setActiveSheetIndex: (value: number) => void;
  previewPolygons: PolygonPayload[];
  jobError: string | null;
  job: JobResponse | null;
  polling: boolean;
};

export function WorkspacePage({
  healthChecking,
  connected,
  resetWorkflow,
  uploadError,
  uploadedFiles,
  fileInputRef,
  uploading,
  handleFilesSelected,
  uploadStatus,
  cleanupResult,
  cleanupError,
  importResult,
  cleanupLoading,
  handleClean,
  cleanupStatus,
  cleanupReadyPartsCount,
  validationErrors,
  form,
  jobLoading,
  handleFormChange,
  handlePartChange,
  handleRemovePart,
  setScaleWarningAcknowledged,
  handleRunJob,
  scaleWarning,
  scaleWarningAcknowledged,
  nestingStatus,
  result,
  canShowResult,
  activeSheetIndex,
  setActiveSheetIndex,
  previewPolygons,
  jobError,
  job,
  polling,
}: WorkspacePageProps) {
  const heroStats = [
    { label: "Uploaded parts", value: `${uploadedFiles.length}` },
    { label: "Ready geometry", value: `${cleanupReadyPartsCount}` },
    { label: "Layouts", value: `${result?.layouts_used ?? result?.layouts.length ?? 0}` },
    { label: "Placed parts", value: `${result?.total_parts_placed ?? result?.parts_placed ?? 0}` },
  ];

  return (
    <div className="min-h-screen px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px]">
        <header className="mb-6 overflow-hidden rounded-[2.5rem] border border-[color:var(--border)] bg-[linear-gradient(135deg,rgba(17,24,39,0.96)_0%,rgba(10,12,16,0.98)_55%,rgba(16,185,129,0.08)_100%)] shadow-panel">
          <div className="grid gap-8 px-6 py-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)] lg:px-8 lg:py-8">
            <div>
              <div className="flex items-center gap-4">
                <LogoSVG className="flex items-center" withWordmark={false} iconClassName="h-8 w-8 shrink-0" />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-300">Industrial Nesting Platform</p>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink md:text-5xl">Nestora</h1>
                </div>
              </div>
              <p className="mt-5 max-w-3xl text-base leading-7 text-slate-300 md:text-lg">
                Production-ready 2D nesting for DXF workflows. Import geometry, validate parts, run mixed placement jobs, and review real material metrics in one branded workspace.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <div className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-300">
                  Dark production workspace
                </div>
                <div className="rounded-full border border-amber-400/20 bg-amber-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-amber-200">
                  Mixed nesting ready
                </div>
                <div className="rounded-full border border-slate-700 bg-white/[0.03] px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-300">
                  Backend-driven metrics
                </div>
              </div>
            </div>
            <div className="rounded-[2rem] border border-[color:var(--border)] bg-black/20 p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-slate-100">Workspace status</div>
                <ConnectionBadge checking={healthChecking} connected={connected} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                {heroStats.map((item) => (
                  <div key={item.label} className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-4">
                    <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{item.label}</div>
                    <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
                  </div>
                ))}
              </div>
              <button
                className="mt-4 w-full rounded-full border border-[color:var(--border)] bg-white/5 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent hover:text-white"
                onClick={() => resetWorkflow()}
                type="button"
              >
                Reset Workspace
              </button>
            </div>
          </div>
        </header>

        {!connected && !healthChecking ? (
          <div className="mb-6">
            <StatusMessage
              message="Backend connection failed. Start the API server and verify VITE_API_BASE_URL."
              tone="error"
            />
          </div>
        ) : null}

        {uploadedFiles.length === 0 ? <EmptyState onBrowseClick={() => fileInputRef.current?.click()} /> : null}

        <div className="mt-6 grid gap-6 xl:grid-cols-[430px_minmax(0,1fr)_350px]">
          <aside className="space-y-6">
            <UploadPanel
              error={uploadError}
              files={uploadedFiles}
              inputRef={fileInputRef}
              loading={uploading}
              onFilesSelected={handleFilesSelected}
              statusMessage={uploadStatus}
            />
            <CleanupPanel
              cleanupResult={cleanupResult}
              error={cleanupError}
              importResult={importResult}
              loading={cleanupLoading}
              onClean={handleClean}
              statusMessage={cleanupStatus}
            />
            <NestingFormPanel
              cleanupReady={cleanupReadyPartsCount > 0}
              errors={validationErrors}
              form={form}
              loading={jobLoading}
              onChange={handleFormChange}
              onPartChange={handlePartChange}
              onRemovePart={handleRemovePart}
              onScaleWarningAcknowledged={setScaleWarningAcknowledged}
              onSubmit={handleRunJob}
              parts={uploadedFiles.map((file) => ({
                id: file.id,
                filename: file.name,
                parsedPolygonCount: file.polygons ?? 0,
                cleanedPolygonCount: file.cleanedPolygons.length,
                units: file.detectedUnits ?? null,
                quantity: file.quantity,
                enabled: file.enabled,
                fillOnly: file.fillOnly,
                hasGeometry: Boolean(file.nestingPolygon),
                cleanupIssue: file.cleanupError,
              }))}
              scaleWarning={scaleWarning}
              scaleWarningAcknowledged={scaleWarningAcknowledged}
              statusMessage={nestingStatus}
              submitLabel={result ? "Improve Result" : "Run Nesting"}
            />
          </aside>

          <main>
            <LayoutViewer
              activeSheetIndex={activeSheetIndex}
              canShowResult={canShowResult}
              debug={result?.debug ?? null}
              layouts={result?.layouts ?? []}
              onSheetChange={setActiveSheetIndex}
              previewPolygons={previewPolygons}
            />
          </main>

          <aside className="space-y-6">
            <JobStatusPanel disconnected={!connected && !healthChecking} error={jobError} job={job} polling={polling} />
            <MetricsPanel result={canShowResult ? result : null} />
          </aside>
        </div>
      </div>
    </div>
  );
}
