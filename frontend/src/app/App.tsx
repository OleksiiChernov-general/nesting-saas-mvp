import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient, ApiError } from "../api/client";
import { HomePage } from "./HomePage";
import { type NestingFormState } from "../features/nesting/NestingFormPanel";
import { type UploadedFileItem } from "../features/upload/UploadPanel";
import { WorkspacePage } from "./WorkspacePage";
import type { CleanGeometryResponse, ImportResponse, JobResponse, NestingResultResponse, PolygonPayload } from "../types/api";
import { parseInteger, parseNonNegativeNumber, parsePositiveNumber } from "../utils/numbers";

const POLLING_INTERVAL_MS = 1500;
const POLLING_TIMEOUT_MS = 300000;
const HOME_LANGUAGE_KEY = "nestora-home-language";

type AppPage = "home" | "workspace";
type HomeLanguage = "en" | "tr" | "uk";

const defaultForm: NestingFormState = {
  nestingMode: "fill_sheet",
  sheetWidth: "100",
  sheetHeight: "100",
  sheetQuantity: "1",
  sheetUnits: "mm",
  gap: "2",
  objective: "MAX_YIELD",
  debug: true,
};

type UploadedImportItem = UploadedFileItem & {
  partId: string;
  response?: ImportResponse;
  cleanupRemoved: number;
  cleanupInvalidShapes: number;
  cleanupError: string | null;
  cleanedPolygons: PolygonPayload[];
  nestingPolygon: PolygonPayload | null;
  quantity: string;
  enabled: boolean;
  fillOnly: boolean;
};

function polygonArea(polygon: PolygonPayload): number {
  let area = 0;
  for (let index = 0; index < polygon.points.length - 1; index += 1) {
    const current = polygon.points[index];
    const next = polygon.points[index + 1];
    area += current.x * next.y - next.x * current.y;
  }
  return Math.abs(area) / 2;
}

function pickPrimaryPolygon(polygons: PolygonPayload[]): PolygonPayload | null {
  if (polygons.length === 0) return null;
  return [...polygons].sort((left, right) => polygonArea(right) - polygonArea(left))[0] ?? null;
}

function resetPartProcessingState(file: UploadedImportItem): UploadedImportItem {
  return {
    ...file,
    cleanupRemoved: 0,
    cleanupInvalidShapes: 0,
    cleanupError: null,
    cleanedPolygons: [],
    nestingPolygon: null,
  };
}

export function App() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const pollTokenRef = useRef(0);

  const [page, setPage] = useState<AppPage>(() => (window.location.hash === "#/workspace" ? "workspace" : "home"));
  const [homeLanguage, setHomeLanguage] = useState<HomeLanguage>(() => {
    const saved = window.localStorage.getItem(HOME_LANGUAGE_KEY);
    return saved === "tr" || saved === "uk" ? saved : "en";
  });
  const [pendingWorkspaceBrowse, setPendingWorkspaceBrowse] = useState(false);
  const [healthChecking, setHealthChecking] = useState(true);
  const [connected, setConnected] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [jobLoading, setJobLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedImportItem[]>([]);
  const [cleanupResult, setCleanupResult] = useState<CleanGeometryResponse | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [result, setResult] = useState<NestingResultResponse | null>(null);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [form, setForm] = useState<NestingFormState>(defaultForm);
  const [scaleWarningAcknowledged, setScaleWarningAcknowledged] = useState(false);

  const resetWorkflow = () => {
    if (pollTimeoutRef.current) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    pollTokenRef.current += 1;
    setPolling(false);
    setUploading(false);
    setCleanupLoading(false);
    setJobLoading(false);
    setUploadError(null);
    setCleanupError(null);
    setJobError(null);
    setUploadedFiles([]);
    setCleanupResult(null);
    setJob(null);
    setResult(null);
    setActiveSheetIndex(0);
    setScaleWarningAcknowledged(false);
  };

  const resetDownstreamState = () => {
    if (pollTimeoutRef.current) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    pollTokenRef.current += 1;
    setPolling(false);
    setCleanupLoading(false);
    setJobLoading(false);
    setCleanupError(null);
    setJobError(null);
    setCleanupResult(null);
    setJob(null);
    setResult(null);
    setActiveSheetIndex(0);
    setScaleWarningAcknowledged(false);
  };

  useEffect(() => {
    const syncPageFromHash = () => {
      setPage(window.location.hash === "#/workspace" ? "workspace" : "home");
    };

    window.addEventListener("hashchange", syncPageFromHash);
    return () => window.removeEventListener("hashchange", syncPageFromHash);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(HOME_LANGUAGE_KEY, homeLanguage);
  }, [homeLanguage]);

  useEffect(() => {
    if (page !== "workspace" || !pendingWorkspaceBrowse) return;
    const timer = window.setTimeout(() => {
      fileInputRef.current?.click();
      setPendingWorkspaceBrowse(false);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [page, pendingWorkspaceBrowse]);

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
    if (!job?.id || (job.state !== "QUEUED" && job.state !== "RUNNING" && job.state !== "CREATED")) {
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

        if (nextJob.state === "SUCCEEDED" || nextJob.state === "PARTIAL") {
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

        if (Date.now() > deadline && (nextJob.state === "QUEUED" || nextJob.state === "RUNNING")) {
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

  const importResult = useMemo<ImportResponse | null>(() => {
    const parsedFiles = uploadedFiles.filter((file) => file.response);
    if (parsedFiles.length === 0) return null;
    return {
      import_id: parsedFiles.map((file) => file.response?.import_id ?? file.id).join(","),
      filename: parsedFiles.length === 1 ? parsedFiles[0].name : `${parsedFiles.length} DXF files`,
      polygons: parsedFiles.flatMap((file) => file.response?.polygons ?? []),
      invalid_shapes: parsedFiles.flatMap((file) => file.response?.invalid_shapes ?? []),
      audit: null,
    };
  }, [uploadedFiles]);

  const cleanupReadyParts = useMemo(
    () => uploadedFiles.filter((file) => file.enabled && file.nestingPolygon),
    [uploadedFiles],
  );

  const validationErrors = useMemo(() => {
    const errors: Partial<Record<keyof NestingFormState | "parts", string>> = {};
    if (!(Number(form.sheetWidth) > 0)) errors.sheetWidth = "Width must be greater than 0.";
    if (!(Number(form.sheetHeight) > 0)) errors.sheetHeight = "Height must be greater than 0.";
    if (!(Number(form.sheetQuantity) >= 1)) errors.sheetQuantity = "Quantity must be at least 1.";
    if (!(Number(form.gap) >= 0)) errors.gap = "Gap must be 0 or greater.";

    const enabledParts = uploadedFiles.filter((file) => file.enabled);
    if (enabledParts.length === 0) {
      errors.parts = "Enable at least one part before running nesting.";
    } else if (!enabledParts.some((file) => file.nestingPolygon)) {
      errors.parts = "At least one enabled part must have a valid cleaned polygon.";
    } else if (form.nestingMode === "batch_quantity" && enabledParts.some((file) => parseInteger(file.quantity, 0) < 1)) {
      errors.parts = "Batch Quantity mode requires quantity >= 1 for every enabled part.";
    }

    return errors;
  }, [form.gap, form.nestingMode, form.sheetHeight, form.sheetQuantity, form.sheetWidth, uploadedFiles]);

  const previewPolygons = cleanupResult?.polygons ?? importResult?.polygons ?? [];
  const canShowResult = Boolean(result && job && (job.state === "SUCCEEDED" || job.state === "PARTIAL"));
  const importAudit = useMemo(() => {
    if (!uploadedFiles.length) return null;
    const audits = uploadedFiles.flatMap((file) => (file.response?.audit ? [file.response.audit] : []));
    if (audits.length === 0) return null;
    const detectedUnits = Array.from(new Set(audits.map((audit) => audit.detected_units).filter(Boolean)));
    const warnings = audits.flatMap((audit) => audit.warnings);
    const maxExtent = Math.max(...audits.map((audit) => audit.geometry_stats.max_extent ?? 0));
    return { detectedUnits, warnings, maxExtent };
  }, [uploadedFiles]);

  const scaleWarning = useMemo(() => {
    if (!importAudit) return null;
    const width = Number(form.sheetWidth);
    const height = Number(form.sheetHeight);
    const sheetMaxExtent = Math.max(Number.isFinite(width) ? width : 0, Number.isFinite(height) ? height : 0);
    if (!(sheetMaxExtent > 0) || !(importAudit.maxExtent > 0)) return importAudit.warnings[0] ?? null;
    const ratio = sheetMaxExtent / importAudit.maxExtent;
    if (ratio < 25) return importAudit.warnings[0] ?? null;
    const units = importAudit.detectedUnits.length ? importAudit.detectedUnits.join(", ") : "unknown units";
    return `Detected source units: ${units}. Largest imported part extent is ${importAudit.maxExtent.toFixed(3)}, while the sheet max extent is ${sheetMaxExtent.toFixed(3)}. Ratio: ${ratio.toFixed(1)}x. This usually means DXF units and sheet units do not match.`;
  }, [form.sheetHeight, form.sheetWidth, importAudit]);

  useEffect(() => {
    setScaleWarningAcknowledged(false);
  }, [scaleWarning]);

  const handleFilesSelected = async (nextFiles: File[]) => {
    if (nextFiles.length === 0) return;

    if (pollTimeoutRef.current) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    pollTokenRef.current += 1;
    setPolling(false);
    setCleanupLoading(false);
    setJobLoading(false);
    setCleanupError(null);
    setJobError(null);
    setCleanupResult(null);
    setJob(null);
    setResult(null);
    setActiveSheetIndex(0);
    setScaleWarningAcknowledged(false);
    setUploadError(null);

    const queuedFiles = nextFiles.map((file, index) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${index}`,
      partId: `part-${Date.now()}-${index + 1}`,
      name: file.name,
      status: "selected" as const,
      polygons: 0,
      invalidShapes: 0,
      error: null,
      detectedUnits: null,
      auditWarning: null,
      cleanupRemoved: 0,
      cleanupInvalidShapes: 0,
      cleanupError: null,
      cleanedPolygons: [],
      nestingPolygon: null,
      quantity: "1",
      enabled: true,
      fillOnly: false,
    }));

    setUploadedFiles((current) => [...current.map(resetPartProcessingState), ...queuedFiles]);
    setUploading(true);

    try {
      for (let index = 0; index < nextFiles.length; index += 1) {
        const nextFile = nextFiles[index];
        const queuedFile = queuedFiles[index];
        setUploadedFiles((current) =>
          current.map((file) => (file.id === queuedFile.id ? { ...file, status: "uploading" } : file)),
        );

        try {
          const response = await apiClient.importFile(nextFile);
          setUploadedFiles((current) =>
            current.map((file) =>
              file.id === queuedFile.id
                ? {
                    ...file,
                    status: "parsed",
                    response,
                    polygons: response.polygons.length,
                    invalidShapes: response.invalid_shapes.length,
                    detectedUnits: response.audit?.detected_units ?? null,
                    auditWarning: response.audit?.warnings[0] ?? null,
                  }
                : file,
            ),
          );
          setConnected(true);
        } catch (error) {
          const message = getReadableError(error, "Upload failed.");
          setUploadedFiles((current) =>
            current.map((file) => (file.id === queuedFile.id ? { ...file, status: "failed", error: message } : file)),
          );
          setUploadError(message);
        }
      }
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

    const nextFiles: UploadedImportItem[] = [];
    let fatalError: string | null = null;

    for (const file of uploadedFiles) {
      if (!file.response) {
        nextFiles.push(resetPartProcessingState(file));
        continue;
      }

      if (file.response.polygons.length === 0) {
        nextFiles.push({
          ...resetPartProcessingState(file),
          cleanupError: "Import produced no valid polygons.",
        });
        continue;
      }

      try {
        const response = await apiClient.cleanGeometry(file.response.polygons);
        const primaryPolygon = pickPrimaryPolygon(response.polygons);
        const cleanedIssue =
          response.polygons.length === 0
            ? "Cleanup removed all polygons."
            : response.polygons.length > 1
              ? "Multiple cleaned polygons found. Nesting uses the largest polygon from this file."
              : null;
        nextFiles.push({
          ...file,
          cleanupRemoved: response.removed,
          cleanupInvalidShapes: response.invalid_shapes.length,
          cleanupError: cleanedIssue,
          cleanedPolygons: response.polygons,
          nestingPolygon: primaryPolygon,
        });
      } catch (error) {
        fatalError = getReadableError(error, "Geometry cleanup failed.");
        nextFiles.push({
          ...resetPartProcessingState(file),
          cleanupError: fatalError,
        });
      }
    }

    setUploadedFiles(nextFiles);
    setCleanupResult({
      polygons: nextFiles.flatMap((file) => file.cleanedPolygons),
      removed: nextFiles.reduce((sum, file) => sum + file.cleanupRemoved, 0),
      invalid_shapes: nextFiles.flatMap((file) => {
        if (!file.cleanupInvalidShapes) return [];
        return Array.from({ length: file.cleanupInvalidShapes }, (_, index) => ({
          source: file.name,
          reason: file.cleanupError ?? `Cleanup warning ${index + 1}`,
        }));
      }),
    });
    setCleanupError(fatalError);
    setConnected(!fatalError);
    setCleanupLoading(false);
  };

  const handleRunJob = async () => {
    if (cleanupReadyParts.length === 0) return;
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
        mode: form.nestingMode,
        previous_job_id: result?.job_id ?? job?.id ?? null,
        parts: cleanupReadyParts.map((part) => ({
          part_id: part.partId,
          filename: part.name,
          quantity: form.nestingMode === "batch_quantity" ? parseInteger(part.quantity, 1) : undefined,
          enabled: part.enabled,
          fill_only: form.nestingMode === "fill_sheet" ? part.fillOnly : false,
          polygon: part.nestingPolygon as PolygonPayload,
        })),
        sheet: { sheet_id: "sheet-1", width, height, quantity, units: form.sheetUnits },
        params: {
          gap,
          rotation: [0, 45, 90, 135, 180, 225, 270, 315],
          objective: form.objective === "MIN_SHEETS" ? "min_sheets" : "maximize_yield",
          debug: form.debug,
          source_units: importAudit?.detectedUnits.join(", ") ?? null,
          source_max_extent: importAudit?.maxExtent ?? null,
        },
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
    resetDownstreamState();
    setForm((current) => ({ ...current, [field]: value }) as NestingFormState);
  };

  const handlePartChange = (partId: string, patch: Partial<Pick<UploadedImportItem, "quantity" | "enabled" | "fillOnly">>) => {
    resetDownstreamState();
    setUploadedFiles((current) =>
      current.map((file) => (file.id === partId ? { ...file, ...patch } : file)),
    );
  };

  const handleRemovePart = (partId: string) => {
    resetDownstreamState();
    setUploadedFiles((current) => current.filter((file) => file.id !== partId));
  };

  const uploadStatus = uploading
    ? "Uploading DXF files to the backend..."
    : importResult
      ? `Upload succeeded. ${uploadedFiles.filter((file) => file.response).length} file(s) are ready for cleanup and part configuration.`
      : uploadedFiles.some((file) => file.status === "failed")
        ? "One or more uploads failed. Review the uploaded-files list."
        : "Step 1: Select one or more DXF files to build a multi-part nesting job.";
  const cleanupStatus = cleanupLoading
    ? "Cleaning geometry for each uploaded part..."
    : cleanupResult && cleanupResult.polygons.length > 0
      ? "Step 2 complete. Part geometry is cleaned and the production workflow is ready."
      : !importResult
        ? "Upload DXF files before cleanup."
        : "Step 2: Run cleanup so each uploaded file has validated nesting geometry.";
  const nestingStatus = jobLoading
    ? "Submitting nesting job..."
    : job?.state === "FAILED"
      ? "Previous job failed. Update inputs if needed and run again."
      : cleanupReadyParts.length > 0
        ? result
          ? "Step 6: Run another bounded optimization pass to try improving the current result."
          : "Step 6: Review the part list, choose the mode, and run nesting."
        : "Cleanup must succeed before nesting.";
  const goToWorkspace = () => {
    window.location.hash = "/workspace";
  };

  const handleHomeUploadClick = () => {
    setPendingWorkspaceBrowse(true);
    goToWorkspace();
  };

  if (page === "home") {
    return (
      <HomePage
        language={homeLanguage}
        onLanguageChange={setHomeLanguage}
        onUploadClick={handleHomeUploadClick}
        onWorkspaceClick={goToWorkspace}
      />
    );
  }

  return (
    <WorkspacePage
      activeSheetIndex={activeSheetIndex}
      canShowResult={canShowResult}
      cleanupError={cleanupError}
      cleanupLoading={cleanupLoading}
      cleanupReadyPartsCount={cleanupReadyParts.length}
      cleanupResult={cleanupResult}
      cleanupStatus={cleanupStatus}
      connected={connected}
      fileInputRef={fileInputRef}
      form={form}
      handleClean={handleClean}
      handleFilesSelected={handleFilesSelected}
      handleFormChange={handleFormChange}
      handlePartChange={handlePartChange}
      handleRemovePart={handleRemovePart}
      handleRunJob={handleRunJob}
      healthChecking={healthChecking}
      importResult={importResult}
      job={job}
      jobError={jobError}
      jobLoading={jobLoading}
      nestingStatus={nestingStatus}
      polling={polling}
      previewPolygons={previewPolygons}
      resetWorkflow={resetWorkflow}
      result={result}
      scaleWarning={scaleWarning}
      scaleWarningAcknowledged={scaleWarningAcknowledged}
      setActiveSheetIndex={setActiveSheetIndex}
      setScaleWarningAcknowledged={setScaleWarningAcknowledged}
      uploadError={uploadError}
      uploadedFiles={uploadedFiles}
      uploading={uploading}
      uploadStatus={uploadStatus}
      validationErrors={validationErrors}
    />
  );
}

function getReadableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
