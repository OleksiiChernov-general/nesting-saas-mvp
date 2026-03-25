import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient, ApiError } from "../api/client";
import { ConnectionBadge } from "../components/ConnectionBadge";
import { EmptyState } from "../components/EmptyState";
import { StatusMessage } from "../components/StatusMessage";
import { MetricsPanel } from "../features/metrics/MetricsPanel";
import { type NestingFormState, NestingFormPanel } from "../features/nesting/NestingFormPanel";
import { JobStatusPanel } from "../features/status/JobStatusPanel";
import { CleanupPanel } from "../features/upload/CleanupPanel";
import { UploadPanel } from "../features/upload/UploadPanel";
import { LayoutViewer } from "../features/viewer/LayoutViewer";
import type { CleanGeometryResponse, ImportResponse, JobResponse, NestingResultResponse } from "../types/api";
import { parseInteger, parseNonNegativeNumber, parsePositiveNumber } from "../utils/numbers";

const POLLING_INTERVAL_MS = 1500;
const POLLING_TIMEOUT_MS = 60000;

const defaultForm: NestingFormState = {
  sheetWidth: "100",
  sheetHeight: "100",
  sheetQuantity: "1",
  gap: "2",
  objective: "MAX_YIELD",
};

export function App() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const pollTokenRef = useRef(0);

  const [healthChecking, setHealthChecking] = useState(true);
  const [connected, setConnected] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [jobLoading, setJobLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const [cleanupResult, setCleanupResult] = useState<CleanGeometryResponse | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [result, setResult] = useState<NestingResultResponse | null>(null);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [form, setForm] = useState<NestingFormState>(defaultForm);

  const resetWorkflow = (keepFile = false) => {
    if (pollTimeoutRef.current) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    pollTokenRef.current += 1;
    setPolling(false);
    if (!keepFile) setFile(null);
    setUploading(false);
    setCleanupLoading(false);
    setJobLoading(false);
    setUploadError(null);
    setCleanupError(null);
    setJobError(null);
    setImportResult(null);
    setCleanupResult(null);
    setJob(null);
    setResult(null);
    setActiveSheetIndex(0);
  };

  useEffect(() => {
    let active = true;
    void apiClient
      .health()
      .then((response) => {
        if (active) setConnected(response.status === "ok");
      })
      .catch(() => {
        if (active) setConnected(false);
      })
      .finally(() => {
        if (active) setHealthChecking(false);
      });

    return () => {
      active = false;
      if (pollTimeoutRef.current) {
        window.clearTimeout(pollTimeoutRef.current);
      }
      pollTokenRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (!job?.id || (job.state !== "CREATED" && job.state !== "RUNNING")) {
      setPolling(false);
      return;
    }

    pollTokenRef.current += 1;
    const token = pollTokenRef.current;
    const deadline = Date.now() + POLLING_TIMEOUT_MS;
    setPolling(true);

    const poll = async (): Promise<void> => {
      try {
        const nextJob = await apiClient.getJob(job.id);
        if (pollTokenRef.current !== token) return;
        setJob(nextJob);

        if (nextJob.state === "SUCCEEDED") {
          const nextResult = await apiClient.getResult(nextJob.id);
          if (pollTokenRef.current !== token) return;
          setResult(nextResult);
          setActiveSheetIndex(0);
          setPolling(false);
          return;
        }

        if (nextJob.state === "FAILED") {
          setResult(null);
          setPolling(false);
          return;
        }

        if (Date.now() > deadline) {
          setJobError("The job took too long to finish. Try again or check the backend worker.");
          setPolling(false);
          return;
        }

        pollTimeoutRef.current = window.setTimeout(() => {
          void poll();
        }, POLLING_INTERVAL_MS);
      } catch (error) {
        if (pollTokenRef.current !== token) return;
        setJobError(getReadableError(error, "Failed to poll job status."));
        setPolling(false);
      }
    };

    void poll();

    return () => {
      if (pollTimeoutRef.current) {
        window.clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
    };
  }, [job?.id, job?.state]);

  const validationErrors = useMemo(() => {
    const errors: Partial<Record<keyof NestingFormState, string>> = {};
    if (!(Number(form.sheetWidth) > 0)) errors.sheetWidth = "Width must be greater than 0.";
    if (!(Number(form.sheetHeight) > 0)) errors.sheetHeight = "Height must be greater than 0.";
    if (!(Number(form.sheetQuantity) >= 1)) errors.sheetQuantity = "Quantity must be at least 1.";
    if (!(Number(form.gap) >= 0)) errors.gap = "Gap must be 0 or greater.";
    return errors;
  }, [form]);

  const previewPolygons = cleanupResult?.polygons ?? importResult?.polygons ?? [];
  const canShowResult = Boolean(result && job?.state === "SUCCEEDED");

  const handleFileChange = (nextFile: File | null) => {
    if (!nextFile) {
      resetWorkflow();
      return;
    }
    void handleUpload(nextFile);
  };

  const handleUpload = async (nextFile = file) => {
    if (!nextFile) return;
    resetWorkflow(true);
    setFile(nextFile);
    setUploading(true);

    try {
      const response = await apiClient.importFile(nextFile);
      setImportResult(response);
      setConnected(true);
    } catch (error) {
      setUploadError(getReadableError(error, "Upload failed."));
      setConnected(false);
    } finally {
      setUploading(false);
    }
  };

  const handleClean = async () => {
    if (!importResult) return;
    setCleanupLoading(true);
    setCleanupError(null);
    setJob(null);
    setResult(null);
    setJobError(null);

    try {
      const response = await apiClient.cleanGeometry(importResult.polygons);
      setCleanupResult(response);
      setConnected(true);
    } catch (error) {
      setCleanupError(getReadableError(error, "Geometry cleanup failed."));
      setConnected(false);
    } finally {
      setCleanupLoading(false);
    }
  };

  const handleRunJob = async () => {
    if (!cleanupResult || cleanupResult.polygons.length === 0) return;
    setJobLoading(true);
    setJobError(null);
    setResult(null);
    setJob(null);

    try {
      const width = parsePositiveNumber(form.sheetWidth, 100);
      const height = parsePositiveNumber(form.sheetHeight, 100);
      const quantity = parseInteger(form.sheetQuantity, 1);
      const gap = parseNonNegativeNumber(form.gap, 0);

      const response = await apiClient.createJob({
        parts: cleanupResult.polygons.map((polygon, index) => ({
          part_id: `part-${index + 1}`,
          quantity: 1,
          polygon,
        })),
        sheets: [{ sheet_id: "sheet-1", width, height, quantity }],
        params: { gap, rotation: [0, 180], objective: form.objective },
      });

      setJob(response);
      setConnected(true);
    } catch (error) {
      setJobError(getReadableError(error, "Failed to create nesting job."));
      setConnected(false);
    } finally {
      setJobLoading(false);
    }
  };

  const handleFormChange = <K extends keyof NestingFormState>(field: K, value: NestingFormState[K]) => {
    setForm((current) => ({ ...current, [field]: value }) as NestingFormState);
  };

  const uploadStatus = uploading
    ? "Uploading DXF to backend..."
    : importResult
      ? `Upload succeeded. ${importResult.polygons.length} polygon(s) ready for cleanup.`
      : file
        ? "DXF selected. Upload will start automatically."
        : "Select a DXF file to begin. Upload starts automatically.";
  const cleanupStatus = cleanupLoading
    ? "Cleaning geometry..."
    : cleanupResult
      ? "Cleanup succeeded. Nesting is now available."
      : !importResult
        ? "Upload a DXF before cleanup."
        : "Run geometry cleanup to validate imported polygons.";
  const nestingStatus = jobLoading
    ? "Submitting nesting job..."
    : job?.state === "FAILED"
      ? "Previous job failed. Update inputs if needed and run again."
      : cleanupResult
        ? "Configure sheet stock and run nesting."
        : "Cleanup must succeed before nesting.";

  return (
    <div className="min-h-screen px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px]">
        <header className="mb-6 flex flex-col gap-4 rounded-[2rem] border border-slate-200 bg-white/80 px-6 py-5 shadow-panel backdrop-blur lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-accent">2D Material Optimization</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">Nesting SaaS MVP</h1>
          </div>
          <div className="flex items-center gap-3">
            <ConnectionBadge checking={healthChecking} connected={connected} />
            <button
              className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
              onClick={() => resetWorkflow()}
              type="button"
            >
              Reset
            </button>
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

        {!importResult && !file ? <EmptyState onBrowseClick={() => fileInputRef.current?.click()} /> : null}

        <div className="mt-6 grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)_320px]">
          <aside className="space-y-6">
            <UploadPanel
              error={uploadError}
              file={file}
              importedFileName={importResult?.filename ?? null}
              inputRef={fileInputRef}
              loading={uploading}
              onFileChange={handleFileChange}
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
              cleanupReady={Boolean(cleanupResult && cleanupResult.polygons.length > 0)}
              errors={validationErrors}
              form={form}
              loading={jobLoading}
              onChange={handleFormChange}
              onSubmit={handleRunJob}
              statusMessage={nestingStatus}
            />
          </aside>

          <main>
            <LayoutViewer
              activeSheetIndex={activeSheetIndex}
              canShowResult={canShowResult}
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

function getReadableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
