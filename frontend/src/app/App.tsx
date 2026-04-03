import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient, ApiError } from "../api/client";
import { HomePage } from "./HomePage";
import { type NestingFormState } from "../features/nesting/NestingFormPanel";
import { type UploadedFileItem } from "../features/upload/UploadPanel";
import { WorkspacePage } from "./WorkspacePage";
import { readStoredLanguage, translate, writeStoredLanguage, type AppLanguage } from "../i18n";
import type { CleanGeometryResponse, ImportResponse, JobResponse, MaterialInput, MaterialRecord, NestingResultResponse, PolygonPayload } from "../types/api";
import { parseInteger, parseNonNegativeNumber, parsePositiveNumber } from "../utils/numbers";

const POLLING_INTERVAL_MS = 1500;
const POLLING_TIMEOUT_MS = 300000;
const SELECTED_MATERIAL_KEY = "nestora-selected-material-id";

type AppPage = "home" | "workspace";
type WorkflowStep = 1 | 2 | 3;

type MaterialStatusState =
  | { kind: "loading" }
  | { kind: "available"; count: number }
  | { kind: "empty" }
  | { kind: "loaded"; name: string }
  | { kind: "saved"; name: string }
  | { kind: "updated"; name: string }
  | { kind: "message"; key: string }
  | { kind: "error"; message: string };

const defaultForm: NestingFormState = {
  selectedMaterialId: "",
  materialName: "",
  thickness: "1",
  costPerSheet: "",
  currency: "",
  materialNotes: "",
  batchId: "",
  batchName: "",
  nestingMode: "fill_sheet",
  sheetWidth: "100",
  sheetHeight: "100",
  sheetQuantity: "1",
  sheetUnits: "mm",
  gap: "2",
  rotationStep: "45",
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
  orderId: string;
  orderName: string;
  priority: string;
};

type GroupedOrder = {
  order_id: string;
  order_name: string | null;
  priority: number | null;
  part_ids: string[];
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
  const [language, setLanguage] = useState<AppLanguage>(() => readStoredLanguage());
  const [pendingWorkspaceBrowse, setPendingWorkspaceBrowse] = useState(false);
  const [healthChecking, setHealthChecking] = useState(true);
  const [connected, setConnected] = useState(false);
  const [materialsLoading, setMaterialsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [jobLoading, setJobLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [materialsStatusState, setMaterialsStatusState] = useState<MaterialStatusState>({ kind: "loading" });
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedImportItem[]>([]);
  const [cleanupResult, setCleanupResult] = useState<CleanGeometryResponse | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [result, setResult] = useState<NestingResultResponse | null>(null);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [form, setForm] = useState<NestingFormState>(defaultForm);
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>(1);
  const [screenOneValidationMessage, setScreenOneValidationMessage] = useState<string | null>(null);
  const [screenOneValidationErrors, setScreenOneValidationErrors] = useState<string[]>([]);
  const [screenOneValidationRunning, setScreenOneValidationRunning] = useState(false);
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
    setWorkflowStep(1);
    setScreenOneValidationMessage(null);
    setScreenOneValidationErrors([]);
    setScreenOneValidationRunning(false);
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
    setScreenOneValidationMessage(null);
    setScreenOneValidationErrors([]);
    setScreenOneValidationRunning(false);
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
    writeStoredLanguage(language);
  }, [language]);

  const t = (key: string, params?: Record<string, string | number>) => translate(language, key, params);

  const materialsStatus = useMemo(() => {
    switch (materialsStatusState.kind) {
      case "loading":
        return t("nesting.loadingMaterials");
      case "available":
        return t("status.materialsAvailable", { count: materialsStatusState.count });
      case "empty":
        return t("status.noMaterials");
      case "loaded":
        return t("status.materialPresetLoaded", { name: materialsStatusState.name });
      case "saved":
        return t("status.materialPresetSaved", { name: materialsStatusState.name });
      case "updated":
        return t("status.materialPresetUpdated", { name: materialsStatusState.name });
      case "message":
        return t(materialsStatusState.key);
      case "error":
        return materialsStatusState.message;
      default:
        return t("nesting.materialHint");
    }
  }, [materialsStatusState, t]);

  useEffect(() => {
    if (form.selectedMaterialId) {
      window.localStorage.setItem(SELECTED_MATERIAL_KEY, form.selectedMaterialId);
      return;
    }
    window.localStorage.removeItem(SELECTED_MATERIAL_KEY);
  }, [form.selectedMaterialId]);

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
    let active = true;
    setMaterialsLoading(true);
    setMaterialsStatusState({ kind: "loading" });
    void apiClient
      .getMaterials()
      .then((response) => {
        if (!active) return;
        setMaterials(response);
        setMaterialsStatusState(response.length > 0 ? { kind: "available", count: response.length } : { kind: "empty" });
      })
      .catch((error) => {
        if (!active) return;
        setMaterialsStatusState({ kind: "error", message: getReadableError(error, t("status.materialPresetsLoadFailed")) });
      })
      .finally(() => {
        if (active) setMaterialsLoading(false);
      });

    return () => {
      active = false;
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
          setJobError(t("status.jobTimedOut"));
          setPolling(false);
          return;
        }

        pollTimeoutRef.current = window.setTimeout(() => {
          void poll();
        }, POLLING_INTERVAL_MS);
      } catch (error) {
        if (pollTokenRef.current !== token) return;
        setJobError(getReadableError(error, t("status.jobPollingFailed")));
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
    if (!form.materialName.trim()) errors.materialName = t("status.materialNameRequired");
    if (!(Number(form.thickness) > 0)) errors.thickness = t("status.thicknessRequired");
    if (!(Number(form.sheetWidth) > 0)) errors.sheetWidth = t("status.widthRequired");
    if (!(Number(form.sheetHeight) > 0)) errors.sheetHeight = t("status.heightRequired");
    if (!(Number(form.sheetQuantity) >= 1)) errors.sheetQuantity = t("status.quantityRequired");
    if (!(Number(form.gap) >= 0)) errors.gap = t("status.gapRequired");
    if (!(Number(form.rotationStep) > 0)) errors.rotationStep = t("status.rotationRequired");

    const enabledParts = uploadedFiles.filter((file) => file.enabled);
    if (enabledParts.length === 0) {
      errors.parts = t("status.enablePart");
    } else if (!enabledParts.some((file) => file.nestingPolygon)) {
      errors.parts = t("status.validPolygonRequired");
    } else if (form.nestingMode === "batch_quantity" && enabledParts.some((file) => parseInteger(file.quantity, 0) < 1)) {
      errors.parts = t("status.batchQuantityRequired");
    }

    return errors;
  }, [form.gap, form.materialName, form.nestingMode, form.rotationStep, form.sheetHeight, form.sheetQuantity, form.sheetWidth, form.thickness, uploadedFiles]);

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
    const units = importAudit.detectedUnits.length ? importAudit.detectedUnits.join(", ") : t("nesting.unknownUnits");
    return t("status.scaleWarningDetected", {
      units,
      partExtent: importAudit.maxExtent.toFixed(3),
      sheetExtent: sheetMaxExtent.toFixed(3),
      ratio: ratio.toFixed(1),
    });
  }, [form.sheetHeight, form.sheetWidth, importAudit, t]);

  useEffect(() => {
    setScaleWarningAcknowledged(false);
  }, [scaleWarning]);

  useEffect(() => {
    if (materials.length === 0) return;
    const savedId = window.localStorage.getItem(SELECTED_MATERIAL_KEY);
    if (!savedId) return;
    const selected = materials.find((item) => item.material_id === savedId);
    if (!selected) return;
    setForm((current) => {
      if (current.selectedMaterialId === selected.material_id) return current;
      return {
        ...current,
        selectedMaterialId: selected.material_id,
        materialName: selected.name,
        thickness: `${selected.thickness}`,
        costPerSheet: selected.cost_per_sheet ? `${selected.cost_per_sheet}` : "",
        currency: selected.currency ?? "",
        materialNotes: selected.notes ?? "",
        sheetWidth: `${selected.sheet_width}`,
        sheetHeight: `${selected.sheet_height}`,
        sheetUnits: selected.units,
        gap: `${selected.kerf}`,
      };
    });
  }, [materials]);

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
    setWorkflowStep(1);
    setScreenOneValidationMessage(null);
    setScreenOneValidationErrors([]);
    setScreenOneValidationRunning(false);
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
      orderId: "",
      orderName: "",
      priority: "",
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
          const message = getReadableError(error, t("status.uploadFailedGeneric"));
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

  const handleClean = async (): Promise<{ cleanup: CleanGeometryResponse | null; errors: string[] }> => {
    if (!importResult) return { cleanup: null, errors: [t("status.uploadBeforeContinue")] };
    setCleanupLoading(true);
    setCleanupError(null);
    setJob(null);
    setResult(null);
    setJobError(null);

    const nextFiles: UploadedImportItem[] = [];
    let fatalError: string | null = null;
    const validationIssues: string[] = [];

    for (const file of uploadedFiles) {
      if (!file.response) {
        nextFiles.push(resetPartProcessingState(file));
        validationIssues.push(`${file.name}: ${t("status.fileImportNotFinished")}`);
        continue;
      }

      if (file.response.polygons.length === 0) {
        const message = t("status.importNoPolygons");
        nextFiles.push({
          ...resetPartProcessingState(file),
          cleanupError: message,
        });
        validationIssues.push(`${file.name}: ${message}`);
        continue;
      }

      try {
        const response = await apiClient.cleanGeometry(file.response.polygons);
        const primaryPolygon = pickPrimaryPolygon(response.polygons);
        const cleanedIssue =
          response.polygons.length === 0
            ? t("status.cleanupRemovedAll")
            : response.polygons.length > 1
              ? t("status.cleanupLargestPolygon")
              : null;
        nextFiles.push({
          ...file,
          cleanupRemoved: response.removed,
          cleanupInvalidShapes: response.invalid_shapes.length,
          cleanupError: cleanedIssue,
          cleanedPolygons: response.polygons,
          nestingPolygon: primaryPolygon,
        });
        if (!primaryPolygon) {
          validationIssues.push(`${file.name}: ${t("status.cleanupRemovedAll")}`);
        } else if (cleanedIssue) {
          validationIssues.push(`${file.name}: ${cleanedIssue}`);
        }
      } catch (error) {
        fatalError = getReadableError(error, t("status.geometryCleanupFailed"));
        nextFiles.push({
          ...resetPartProcessingState(file),
          cleanupError: fatalError,
        });
        validationIssues.push(`${file.name}: ${fatalError}`);
      }
    }

    setUploadedFiles(nextFiles);
    const nextCleanupResult = cleanupResultFromFiles(nextFiles);
    setCleanupResult(nextCleanupResult);
    setCleanupError(fatalError);
    setConnected(!fatalError);
    setCleanupLoading(false);
    return { cleanup: fatalError ? null : nextCleanupResult, errors: validationIssues };
  };

  const handleValidateUploadsAndContinue = async () => {
    if (uploadedFiles.length === 0) {
      setScreenOneValidationMessage(t("status.uploadBeforeContinue"));
      setScreenOneValidationErrors([t("status.noFilesYet")]);
      return;
    }

    const importFailures = uploadedFiles
      .filter((file) => !file.response || file.status === "failed")
      .map((file) => `${file.name}: ${file.error ?? t("status.fileImportFailed")}`);
    if (importFailures.length > 0) {
      setScreenOneValidationMessage(t("status.someFilesFailed"));
      setScreenOneValidationErrors(importFailures);
      return;
    }

    setScreenOneValidationRunning(true);
    setScreenOneValidationMessage(t("status.validating"));
    setScreenOneValidationErrors([]);

    const { cleanup, errors } = await handleClean();
    setScreenOneValidationRunning(false);

    if (!cleanup || cleanup.polygons.length === 0) {
      setScreenOneValidationMessage(t("status.validationFailed"));
      setScreenOneValidationErrors(
        errors.length > 0 ? errors : [t("status.noNestablePolygons")],
      );
      setWorkflowStep(1);
      return;
    }

    setScreenOneValidationMessage(t("status.validationPassed", { count: cleanup.polygons.length }));
      setScreenOneValidationErrors(
        errors.filter(
          (message) =>
            message.includes(t("status.cleanupRemovedAll")) ||
            message.includes(t("status.fileImportNotFinished")) ||
            message.includes(t("status.fileImportFailed")),
        ),
      );
    setWorkflowStep(2);
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
      const rotationStep = Math.max(1, Math.min(360, parseInteger(form.rotationStep, 45)));
      const rotation: Array<0 | 45 | 90 | 135 | 180 | 225 | 270 | 315> = [0, 45, 90, 135, 180, 225, 270, 315].filter(
        (angle) => angle % rotationStep === 0,
      ) as Array<0 | 45 | 90 | 135 | 180 | 225 | 270 | 315>;
      const partPayload = cleanupReadyParts.map((part) => ({
        part_id: part.partId,
        filename: part.name,
        quantity: form.nestingMode === "batch_quantity" ? parseInteger(part.quantity, 1) : undefined,
        enabled: part.enabled,
        fill_only: form.nestingMode === "fill_sheet" ? part.fillOnly : false,
        order_id: normalizeOrderId(part),
        order_name: normalizeOrderName(part),
        priority: parseOptionalPriority(part.priority),
        polygon: part.nestingPolygon as PolygonPayload,
      }));
      const groupedOrders = buildBatchOrders(partPayload);

      const response = await apiClient.createJob({
        mode: form.nestingMode,
        previous_job_id: result?.job_id ?? job?.id ?? null,
        parts: partPayload,
        sheet: { sheet_id: "sheet-1", width, height, quantity, units: form.sheetUnits },
        material: {
          material_id: form.selectedMaterialId || undefined,
          name: form.materialName.trim(),
          thickness: parsePositiveNumber(form.thickness, 1),
          sheet_width: width,
          sheet_height: height,
          units: form.sheetUnits,
          kerf: gap,
          cost_per_sheet: parseNonNegativeNumber(form.costPerSheet, 0) > 0 ? parseNonNegativeNumber(form.costPerSheet, 0) : null,
          currency: form.currency.trim() || null,
          notes: form.materialNotes.trim() || null,
        },
        batch: {
          batch_id: form.batchId.trim() || "batch-current",
          batch_name: form.batchName.trim() || "Current batch",
          orders: groupedOrders,
        },
        params: {
          gap,
          rotation: rotation.length > 0 ? rotation : [0, 45, 90, 135, 180, 225, 270, 315],
          objective: form.objective === "MIN_SHEETS" ? "min_sheets" : "maximize_yield",
          debug: form.debug,
          source_units: importAudit?.detectedUnits.join(", ") ?? null,
          source_max_extent: importAudit?.maxExtent ?? null,
        },
      });

      setJob(response);
      setConnected(true);
      setWorkflowStep(3);
    } catch (error) {
      setJobError(getReadableError(error, t("status.createJobFailed")));
      setConnected(false);
    } finally {
      setJobLoading(false);
    }
  };

  const handleFormChange = <K extends keyof NestingFormState>(field: K, value: NestingFormState[K]) => {
    if (field === "selectedMaterialId") {
      const materialId = String(value);
      const selected = materials.find((item) => item.material_id === materialId);
      if (!selected) {
        resetDownstreamState();
        setForm((current) => ({ ...current, selectedMaterialId: "" }));
        return;
      }
      applyMaterialToForm(selected);
      setMaterialsStatusState({ kind: "loaded", name: selected.name });
      return;
    }
    resetDownstreamState();
    setForm((current) => ({ ...current, [field]: value }) as NestingFormState);
  };

  const materialPayloadFromForm = (): MaterialInput => ({
    material_id: form.selectedMaterialId || "",
    name: form.materialName.trim(),
    thickness: parsePositiveNumber(form.thickness, 1),
    sheet_width: parsePositiveNumber(form.sheetWidth, 100),
    sheet_height: parsePositiveNumber(form.sheetHeight, 100),
    units: form.sheetUnits,
    kerf: parseNonNegativeNumber(form.gap, 0),
    cost_per_sheet: parseNonNegativeNumber(form.costPerSheet, 0) > 0 ? parseNonNegativeNumber(form.costPerSheet, 0) : null,
    currency: form.currency.trim() || null,
    notes: form.materialNotes.trim() || null,
  });

  const applyMaterialToForm = (material: MaterialRecord) => {
    resetDownstreamState();
    setForm((current) => ({
      ...current,
      selectedMaterialId: material.material_id,
      materialName: material.name,
      thickness: `${material.thickness}`,
      costPerSheet: material.cost_per_sheet ? `${material.cost_per_sheet}` : "",
      currency: material.currency ?? "",
      materialNotes: material.notes ?? "",
      sheetWidth: `${material.sheet_width}`,
      sheetHeight: `${material.sheet_height}`,
      sheetUnits: material.units,
      gap: `${material.kerf}`,
    }));
  };

  const handleCreateMaterial = async () => {
    if (!form.materialName.trim()) {
      setMaterialsStatusState({ kind: "message", key: "status.materialNameRequiredForPreset" });
      return;
    }
    setMaterialsLoading(true);
    try {
      const created = await apiClient.createMaterial({ ...materialPayloadFromForm(), material_id: undefined });
      setMaterials((current) => [...current, created]);
      applyMaterialToForm(created);
      setMaterialsStatusState({ kind: "saved", name: created.name });
      setConnected(true);
    } catch (error) {
      setMaterialsStatusState({ kind: "error", message: getReadableError(error, t("status.materialPresetSaveFailed")) });
      setConnected(false);
    } finally {
      setMaterialsLoading(false);
    }
  };

  const handleUpdateMaterial = async () => {
    if (!form.selectedMaterialId) {
      setMaterialsStatusState({ kind: "message", key: "status.materialPresetSelectBeforeUpdate" });
      return;
    }
    setMaterialsLoading(true);
    try {
      const updated = await apiClient.updateMaterial(form.selectedMaterialId, materialPayloadFromForm());
      setMaterials((current) => current.map((item) => (item.material_id === updated.material_id ? updated : item)));
      applyMaterialToForm(updated);
      setMaterialsStatusState({ kind: "updated", name: updated.name });
      setConnected(true);
    } catch (error) {
      setMaterialsStatusState({ kind: "error", message: getReadableError(error, t("status.materialPresetUpdateFailed")) });
      setConnected(false);
    } finally {
      setMaterialsLoading(false);
    }
  };

  const handlePartChange = (
    partId: string,
    patch: Partial<Pick<UploadedImportItem, "quantity" | "enabled" | "fillOnly" | "orderId" | "orderName" | "priority">>,
  ) => {
    resetDownstreamState();
    setUploadedFiles((current) =>
      current.map((file) => (file.id === partId ? { ...file, ...patch } : file)),
    );
  };

  const handleUploadPartMetaChange = (partId: string, patch: Partial<Pick<UploadedImportItem, "orderId" | "orderName" | "priority">>) => {
    resetDownstreamState();
    setUploadedFiles((current) => current.map((file) => (file.id === partId ? { ...file, ...patch } : file)));
  };

  const handleRemovePart = (partId: string) => {
    resetDownstreamState();
    setUploadedFiles((current) => current.filter((file) => file.id !== partId));
  };

  const uploadStatus = uploading
    ? t("status.uploadStatusUploading")
    : importResult
      ? t("status.uploadStatusSuccess", { count: uploadedFiles.filter((file) => file.response).length })
      : uploadedFiles.some((file) => file.status === "failed")
        ? t("status.uploadStatusFailed")
        : t("status.uploadStatusInitial");
  const cleanupStatus = cleanupLoading
    ? t("status.cleanupStatusRunning")
    : cleanupResult && cleanupResult.polygons.length > 0
      ? t("status.cleanupStatusComplete")
      : !importResult
        ? t("status.cleanupStatusBeforeUpload")
        : t("status.cleanupStatusWaiting");
  const nestingStatus = jobLoading
    ? t("status.nestingStatusSubmitting")
    : job?.state === "FAILED"
      ? t("status.nestingStatusFailed")
      : cleanupReadyParts.length > 0
        ? result
          ? t("status.nestingStatusRepeat")
          : t("status.nestingStatusReady")
        : t("status.nestingStatusBlocked");
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
        language={language}
        onLanguageChange={setLanguage}
        onUploadClick={handleHomeUploadClick}
        onWorkspaceClick={goToWorkspace}
        t={t}
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
      cleanupStatus={cleanupStatus}
      connected={connected}
      fileInputRef={fileInputRef}
      form={form}
      handleFilesSelected={handleFilesSelected}
      handleUploadPartMetaChange={handleUploadPartMetaChange}
      handleCreateMaterial={handleCreateMaterial}
      handleFormChange={handleFormChange}
      handlePartChange={handlePartChange}
      handleRemovePart={handleRemovePart}
      handleRunJob={handleRunJob}
      handleUpdateMaterial={handleUpdateMaterial}
      handleValidateUploadsAndContinue={handleValidateUploadsAndContinue}
      healthChecking={healthChecking}
      importResult={importResult}
      job={job}
      jobError={jobError}
      jobLoading={jobLoading}
      materials={materials}
      materialsLoading={materialsLoading}
      materialsStatus={materialsStatus}
      nestingStatus={nestingStatus}
      polling={polling}
      previewPolygons={previewPolygons}
      resetWorkflow={resetWorkflow}
      result={result}
      screenOneValidationErrors={screenOneValidationErrors}
      screenOneValidationMessage={screenOneValidationMessage}
      screenOneValidationRunning={screenOneValidationRunning}
      scaleWarning={scaleWarning}
      scaleWarningAcknowledged={scaleWarningAcknowledged}
      setActiveSheetIndex={setActiveSheetIndex}
      setScaleWarningAcknowledged={setScaleWarningAcknowledged}
      uploadError={uploadError}
      uploadedFiles={uploadedFiles}
      uploading={uploading}
      uploadStatus={uploadStatus}
      validationErrors={validationErrors}
      workflowStep={workflowStep}
      setWorkflowStep={setWorkflowStep}
      language={language}
      setLanguage={setLanguage}
      t={t}
    />
  );
}

function normalizeOrderId(file: Pick<UploadedImportItem, "orderId" | "orderName">): string {
  const orderId = file.orderId.trim();
  const orderName = file.orderName.trim();
  return orderId || orderName;
}

function normalizeOrderName(file: Pick<UploadedImportItem, "orderId" | "orderName">): string | null {
  const orderName = file.orderName.trim();
  if (orderName) return orderName;
  return null;
}

function parseOptionalPriority(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function buildBatchOrders(
  parts: Array<{ part_id: string; order_id?: string | null; order_name?: string | null; priority?: number | null }>,
): GroupedOrder[] {
  const orders = new Map<string, GroupedOrder>();
  for (const part of parts) {
    const orderId = (part.order_id ?? "").trim();
    if (!orderId) continue;
    const current = orders.get(orderId) ?? {
      order_id: orderId,
      order_name: part.order_name ?? null,
      priority: part.priority ?? null,
      part_ids: [],
    };
    if (!current.order_name && part.order_name) current.order_name = part.order_name;
    if (current.priority === null && part.priority !== null && part.priority !== undefined) current.priority = part.priority;
    current.part_ids.push(part.part_id);
    orders.set(orderId, current);
  }
  return Array.from(orders.values()).sort((left, right) =>
    (left.order_name || left.order_id).localeCompare(right.order_name || right.order_id),
  );
}

function cleanupResultFromFiles(files: UploadedImportItem[]): CleanGeometryResponse {
  return {
    polygons: files.flatMap((file) => file.cleanedPolygons),
    removed: files.reduce((sum, file) => sum + file.cleanupRemoved, 0),
    invalid_shapes: files.flatMap((file) => {
      if (!file.cleanupInvalidShapes) return [];
      return Array.from({ length: file.cleanupInvalidShapes }, (_, index) => ({
        source: file.name,
        reason: file.cleanupError ?? `Cleanup warning ${index + 1}`,
      }));
    }),
  };
}

function getReadableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
