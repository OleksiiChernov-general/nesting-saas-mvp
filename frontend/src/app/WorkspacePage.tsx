import type { RefObject } from "react";

import { ConnectionBadge } from "../components/ConnectionBadge";
import { EmptyState } from "../components/EmptyState";
import { LanguageSelector } from "../components/LanguageSelector";
import { LogoSVG } from "../components/LogoSVG";
import { Panel } from "../components/Panel";
import { StatusMessage } from "../components/StatusMessage";
import { MetricsPanel } from "../features/metrics/MetricsPanel";
import { type NestingFormState, type NestingPartDraft, NestingFormPanel } from "../features/nesting/NestingFormPanel";
import { JobStatusPanel } from "../features/status/JobStatusPanel";
import { type UploadedFileItem, UploadPanel } from "../features/upload/UploadPanel";
import { LayoutViewer } from "../features/viewer/LayoutViewer";
import { type AppLanguage, type Translate } from "../i18n";
import type { ImportResponse, JobResponse, MaterialRecord, NestingResultResponse, PolygonPayload } from "../types/api";
import { formatNumber, formatPercent } from "../utils/numbers";

type WorkflowStep = 1 | 2 | 3;

type OrderGroupSummary = {
  orderId: string;
  orderName: string;
  priority: string;
  partCount: number;
};

type WorkspaceUploadItem = UploadedFileItem & {
  quantity: string;
  enabled: boolean;
  fillOnly: boolean;
  orderId: string;
  orderName: string;
  priority: string;
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
  handleFilesSelected: (files: File[]) => Promise<void>;
  handleUploadPartMetaChange: (partId: string, patch: Partial<Pick<WorkspaceUploadItem, "orderId" | "orderName" | "priority">>) => void;
  uploadStatus: string;
  cleanupError: string | null;
  importResult: ImportResponse | null;
  materials: MaterialRecord[];
  materialsLoading: boolean;
  materialsStatus: string;
  cleanupLoading: boolean;
  cleanupStatus: string;
  cleanupReadyPartsCount: number;
  validationErrors: Partial<Record<keyof NestingFormState | "parts", string>>;
  form: NestingFormState;
  handleCreateMaterial: () => Promise<void>;
  jobLoading: boolean;
  handleFormChange: (name: keyof NestingFormState, value: string | boolean) => void;
  handlePartChange: (partId: string, patch: Partial<Pick<NestingPartDraft, "quantity" | "enabled" | "fillOnly" | "orderId" | "orderName" | "priority">>) => void;
  handleRemovePart: (partId: string) => void;
  setScaleWarningAcknowledged: (value: boolean) => void;
  handleRunJob: () => Promise<void>;
  handleUpdateMaterial: () => Promise<void>;
  handleValidateUploadsAndContinue: () => Promise<void>;
  screenOneValidationMessage: string | null;
  screenOneValidationErrors: string[];
  screenOneValidationRunning: boolean;
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
  workflowStep: WorkflowStep;
  setWorkflowStep: (value: WorkflowStep) => void;
  language: AppLanguage;
  setLanguage: (value: AppLanguage) => void;
  t: Translate;
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
  handleUploadPartMetaChange,
  uploadStatus,
  cleanupError,
  importResult,
  materials,
  materialsLoading,
  materialsStatus,
  cleanupLoading,
  cleanupStatus,
  cleanupReadyPartsCount,
  validationErrors,
  form,
  handleCreateMaterial,
  jobLoading,
  handleFormChange,
  handlePartChange,
  handleRemovePart,
  setScaleWarningAcknowledged,
  handleRunJob,
  handleUpdateMaterial,
  handleValidateUploadsAndContinue,
  screenOneValidationMessage,
  screenOneValidationErrors,
  screenOneValidationRunning,
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
  workflowStep,
  setWorkflowStep,
  language,
  setLanguage,
  t,
}: WorkspacePageProps) {
  const heroStats = [
    { label: t("workspace.statUploaded"), value: `${uploadedFiles.length}` },
    { label: t("workspace.statValidated"), value: `${cleanupReadyPartsCount}` },
    { label: t("workspace.statRun"), value: `${result?.run_number ?? job?.run_number ?? 0}` },
    { label: t("workspace.statPlaced"), value: `${result?.total_parts_placed ?? result?.parts_placed ?? 0}` },
  ];

  const stepCards: Array<{ step: WorkflowStep; label: string; title: string }> = [
    { step: 1, label: t("workspace.step1"), title: t("workspace.step1Title") },
    { step: 2, label: t("workspace.step2"), title: t("workspace.step2Title") },
    { step: 3, label: t("workspace.step3"), title: t("workspace.step3Title") },
  ];

  const stepDescription =
    workflowStep === 1
      ? t("workspace.step1Title")
      : workflowStep === 2
        ? t("workspace.step2Title")
        : t("workspace.step3Title");

  const groupedOrders = uploadedFiles.reduce<OrderGroupSummary[]>((groups, file) => {
    const orderId = file.orderId.trim();
    const orderName = file.orderName.trim();
    const key = orderId || orderName;
    if (!key) return groups;
    const existing = groups.find((group) => group.orderId === key);
    if (existing) {
      existing.partCount += 1;
      if (!existing.orderName && orderName) existing.orderName = orderName;
      if (!existing.priority && file.priority.trim()) existing.priority = file.priority.trim();
      return groups;
    }
    groups.push({
      orderId: key,
      orderName,
      priority: file.priority.trim(),
      partCount: 1,
    });
    return groups;
  }, []);

  return (
    <div className="min-h-screen px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px]">
        <header className="mb-6 overflow-hidden rounded-[2.5rem] border border-[color:var(--border)] bg-[linear-gradient(135deg,rgba(17,24,39,0.96)_0%,rgba(10,12,16,0.98)_55%,rgba(16,185,129,0.08)_100%)] shadow-panel">
          <div className="grid gap-8 px-6 py-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)] lg:px-8 lg:py-8">
            <div>
              <div className="flex items-center gap-4">
                <LogoSVG className="flex items-center" withWordmark={false} iconClassName="h-8 w-8 shrink-0" />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-300">{t("workspace.badge")}</p>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink md:text-5xl">Nestora</h1>
                </div>
              </div>
              <p className="mt-5 max-w-3xl text-base leading-7 text-slate-300 md:text-lg">
                {t("workspace.description")}
              </p>
              <div className="mt-6 grid gap-3 md:grid-cols-3">
                {stepCards.map((item) => {
                  const active = workflowStep === item.step;
                  const complete = workflowStep > item.step;
                  return (
                    <button
                      key={item.step}
                      className={`rounded-[1.5rem] border px-4 py-4 text-left transition ${
                        active
                          ? "border-emerald-300 bg-emerald-500/12"
                          : complete
                            ? "border-sky-400/30 bg-sky-500/10"
                            : "border-[color:var(--border)] bg-white/[0.03]"
                      }`}
                      disabled={item.step > workflowStep && item.step !== 1}
                      onClick={() => {
                        if (item.step <= workflowStep) setWorkflowStep(item.step);
                      }}
                      type="button"
                    >
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{item.label}</div>
                      <div className="mt-2 text-base font-semibold text-slate-100">{item.title}</div>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="rounded-[2rem] border border-[color:var(--border)] bg-black/20 p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-slate-100">{t("workspace.workflowStatus")}</div>
                <ConnectionBadge checking={healthChecking} connected={connected} t={t} />
              </div>
              <LanguageSelector
                className="mb-4 w-full rounded-2xl border border-[color:var(--border)] bg-[color:var(--card-bg)] px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-emerald-400"
                language={language}
                onLanguageChange={setLanguage}
                t={t}
              />
              <div className="grid grid-cols-2 gap-3">
                {heroStats.map((item) => (
                  <div key={item.label} className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-4">
                    <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{item.label}</div>
                    <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm text-slate-300">
                {stepDescription}
              </div>
              <button
                className="mt-4 w-full rounded-full border border-[color:var(--border)] bg-white/5 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent hover:text-white"
                onClick={() => resetWorkflow()}
                type="button"
              >
                {t("common.resetWorkspace")}
              </button>
            </div>
          </div>
        </header>

        {!connected && !healthChecking ? (
          <div className="mb-6">
            <StatusMessage
              message={t("workspace.backendConnectionFailed")}
              tone="error"
            />
          </div>
        ) : null}

        {workflowStep === 1 ? (
          <ScreenOne
            cleanupError={cleanupError}
            cleanupLoading={cleanupLoading}
            cleanupStatus={cleanupStatus}
            fileInputRef={fileInputRef}
            handleFilesSelected={handleFilesSelected}
            handleUploadPartMetaChange={handleUploadPartMetaChange}
            handleValidateUploadsAndContinue={handleValidateUploadsAndContinue}
            importResult={importResult}
            previewPolygons={previewPolygons}
            screenOneValidationErrors={screenOneValidationErrors}
            screenOneValidationMessage={screenOneValidationMessage}
            screenOneValidationRunning={screenOneValidationRunning}
            uploadError={uploadError}
            uploadedFiles={uploadedFiles}
            uploading={uploading}
            uploadStatus={uploadStatus}
            t={t}
          />
        ) : null}

        {workflowStep === 2 ? (
          <ScreenTwo
            cleanupReadyPartsCount={cleanupReadyPartsCount}
            form={form}
            handleCreateMaterial={handleCreateMaterial}
            handleFormChange={handleFormChange}
            handlePartChange={handlePartChange}
            handleRemovePart={handleRemovePart}
            jobLoading={jobLoading}
            materials={materials}
            materialsLoading={materialsLoading}
            materialsStatus={materialsStatus}
            result={result}
            scaleWarning={scaleWarning}
            scaleWarningAcknowledged={scaleWarningAcknowledged}
            setScaleWarningAcknowledged={setScaleWarningAcknowledged}
            setWorkflowStep={setWorkflowStep}
            handleUpdateMaterial={handleUpdateMaterial}
            uploadedFiles={uploadedFiles}
            validationErrors={validationErrors}
            groupedOrders={groupedOrders}
            t={t}
          />
        ) : null}

        {workflowStep === 3 ? (
          <ScreenThree
            activeSheetIndex={activeSheetIndex}
            canShowResult={canShowResult}
            form={form}
            handleRunJob={handleRunJob}
            job={job}
            jobError={jobError}
            jobLoading={jobLoading}
            nestingStatus={nestingStatus}
            polling={polling}
            previewPolygons={previewPolygons}
            result={result}
            setActiveSheetIndex={setActiveSheetIndex}
            setWorkflowStep={setWorkflowStep}
            groupedOrders={groupedOrders}
            t={t}
          />
        ) : null}

        {uploadedFiles.length === 0 && workflowStep === 1 ? <EmptyState onBrowseClick={() => fileInputRef.current?.click()} t={t} /> : null}
      </div>
    </div>
  );
}

type ScreenOneProps = {
  uploadError: string | null;
  uploadedFiles: WorkspaceUploadItem[];
  fileInputRef: RefObject<HTMLInputElement | null>;
  uploading: boolean;
  handleFilesSelected: (files: File[]) => Promise<void>;
  handleUploadPartMetaChange: (partId: string, patch: Partial<Pick<WorkspaceUploadItem, "orderId" | "orderName" | "priority">>) => void;
  uploadStatus: string;
  importResult: ImportResponse | null;
  cleanupLoading: boolean;
  cleanupStatus: string;
  cleanupError: string | null;
  handleValidateUploadsAndContinue: () => Promise<void>;
  screenOneValidationMessage: string | null;
  screenOneValidationErrors: string[];
  screenOneValidationRunning: boolean;
  previewPolygons: PolygonPayload[];
  t: Translate;
};

function ScreenOne({
  uploadError,
  uploadedFiles,
  fileInputRef,
  uploading,
  handleFilesSelected,
  handleUploadPartMetaChange,
  uploadStatus,
  importResult,
  cleanupLoading,
  cleanupStatus,
  cleanupError,
  handleValidateUploadsAndContinue,
  screenOneValidationMessage,
  screenOneValidationErrors,
  screenOneValidationRunning,
  previewPolygons,
  t,
}: ScreenOneProps) {
  return (
    <div className="grid gap-6 xl:grid-cols-[430px_minmax(0,1fr)]">
      <aside className="space-y-6">
        <UploadPanel
          error={uploadError}
          files={uploadedFiles}
          inputRef={fileInputRef}
          loading={uploading}
          onFilesSelected={handleFilesSelected}
          onPartMetaChange={handleUploadPartMetaChange}
          statusMessage={uploadStatus}
          t={t}
        />
        <Panel title={t("screen1.validationGate")} subtitle={t("screen1.validationGateSubtitle")}>
          <StatusMessage
            message={screenOneValidationMessage ?? cleanupStatus}
            tone={screenOneValidationErrors.length > 0 || cleanupError ? "error" : importResult ? "neutral" : "warning"}
          />
          {screenOneValidationErrors.length > 0 ? (
            <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {screenOneValidationErrors.map((message) => (
                <div key={message}>{message}</div>
              ))}
            </div>
          ) : null}
          <button
            className="w-full rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:shadow-none"
            disabled={uploadedFiles.length === 0 || uploading || cleanupLoading || screenOneValidationRunning}
            onClick={handleValidateUploadsAndContinue}
            type="button"
          >
            {screenOneValidationRunning || cleanupLoading ? t("screen1.validating") : t("common.next")}
          </button>
        </Panel>
      </aside>

      <main className="space-y-6">
        <Panel title={t("screen1.summary")} subtitle={t("screen1.summarySubtitle")}>
          <div className="grid gap-4 md:grid-cols-2">
            <SummaryCard label={t("screen1.files")} value={`${uploadedFiles.length}`} />
            <SummaryCard label={t("screen1.polygons")} value={`${importResult?.polygons.length ?? 0}`} />
            <SummaryCard label={t("screen1.queued")} value={uploadedFiles.length > 0 ? t("common.yes") : t("common.no")} />
            <SummaryCard label={t("screen1.ready")} value={previewPolygons.length > 0 ? t("common.yes") : t("common.no")} />
          </div>
        </Panel>
        <LayoutViewer
          activeSheetIndex={0}
          canShowResult={false}
          debug={null}
          layouts={[]}
          onSheetChange={() => undefined}
          previewPolygons={previewPolygons}
          t={t}
        />
      </main>
    </div>
  );
}

type ScreenTwoProps = {
  cleanupReadyPartsCount: number;
  form: NestingFormState;
  handleCreateMaterial: () => Promise<void>;
  handleFormChange: (name: keyof NestingFormState, value: string | boolean) => void;
  handlePartChange: (partId: string, patch: Partial<Pick<NestingPartDraft, "quantity" | "enabled" | "fillOnly" | "orderId" | "orderName" | "priority">>) => void;
  handleRemovePart: (partId: string) => void;
  jobLoading: boolean;
  materials: MaterialRecord[];
  materialsLoading: boolean;
  materialsStatus: string;
  result: NestingResultResponse | null;
  scaleWarning: string | null;
  scaleWarningAcknowledged: boolean;
  setScaleWarningAcknowledged: (value: boolean) => void;
  setWorkflowStep: (value: WorkflowStep) => void;
  handleUpdateMaterial: () => Promise<void>;
  uploadedFiles: WorkspaceUploadItem[];
  validationErrors: Partial<Record<keyof NestingFormState | "parts", string>>;
  groupedOrders: OrderGroupSummary[];
  t: Translate;
};

function ScreenTwo({
  cleanupReadyPartsCount,
  form,
  handleCreateMaterial,
  handleFormChange,
  handlePartChange,
  handleRemovePart,
  jobLoading,
  materials,
  materialsLoading,
  materialsStatus,
  result,
  scaleWarning,
  scaleWarningAcknowledged,
  setScaleWarningAcknowledged,
  setWorkflowStep,
  handleUpdateMaterial,
  uploadedFiles,
  validationErrors,
  groupedOrders,
  t,
}: ScreenTwoProps) {
  const hasErrors = Object.values(validationErrors).some(Boolean);
  const blockedByScaleWarning = Boolean(scaleWarning && !scaleWarningAcknowledged);
  const canContinue = cleanupReadyPartsCount > 0 && !hasErrors && !blockedByScaleWarning && !jobLoading;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_350px]">
      <main className="space-y-6">
        <NestingFormPanel
          cleanupReady={cleanupReadyPartsCount > 0}
          errors={validationErrors}
          form={form}
          loading={jobLoading}
          materials={materials}
          materialsLoading={materialsLoading}
          materialsStatus={materialsStatus}
          groupedOrders={groupedOrders}
          onChange={handleFormChange}
          onCreateMaterial={() => void handleCreateMaterial()}
          onPartChange={handlePartChange}
          onRemovePart={handleRemovePart}
          onScaleWarningAcknowledged={setScaleWarningAcknowledged}
          onSubmit={() => setWorkflowStep(3)}
          onUpdateMaterial={() => void handleUpdateMaterial()}
          t={t}
          parts={uploadedFiles.map((file) => ({
            id: file.id,
            filename: file.name,
            parsedPolygonCount: file.polygons ?? 0,
            cleanedPolygonCount: file.cleanedPolygons.length,
            units: file.detectedUnits ?? null,
            quantity: file.quantity,
            enabled: file.enabled,
            fillOnly: file.fillOnly,
            orderId: file.orderId,
            orderName: file.orderName,
            priority: file.priority,
            hasGeometry: Boolean(file.nestingPolygon),
            cleanupIssue: file.cleanupError,
          }))}
          scaleWarning={scaleWarning}
          scaleWarningAcknowledged={scaleWarningAcknowledged}
          statusMessage={hasErrors ? t("status.resolveErrors") : t("status.parametersPreserved")}
          submitLabel={t("common.next")}
        />
      </main>
      <aside className="space-y-6">
        <Panel title={t("screen2.summary")} subtitle={t("screen2.summarySubtitle")}>
          <div className="space-y-3">
            <SummaryCard label={t("nesting.materialName")} value={form.materialName || t("common.notSet")} />
            <SummaryCard label={t("nesting.thickness")} value={`${form.thickness || "0"} ${form.sheetUnits}`} />
            <SummaryCard label={t("screen2.sheet")} value={`${form.sheetWidth || "0"} x ${form.sheetHeight || "0"} ${form.sheetUnits}`} />
            <SummaryCard label={t("nesting.rotationStep")} value={`${form.rotationStep} ${t("screen2.degrees")}`} />
          </div>
        </Panel>
        <Panel title={t("screen2.navigation")} subtitle={t("screen2.navigationSubtitle")}>
          <div className="flex gap-3">
            <button
              className="flex-1 rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent"
              onClick={() => setWorkflowStep(1)}
              type="button"
            >
              {t("common.back")}
            </button>
            <button
              className="flex-1 rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700"
              disabled={!canContinue}
              onClick={() => setWorkflowStep(3)}
              type="button"
            >
              {t("common.next")}
            </button>
          </div>
          {blockedByScaleWarning ? <div className="mt-3 text-xs text-amber-300">{t("screen2.scaleWarning")}</div> : null}
          {result ? <div className="mt-3 text-xs text-slate-400">{t("screen2.previousRun")}</div> : null}
        </Panel>
      </aside>
    </div>
  );
}

type ScreenThreeProps = {
  activeSheetIndex: number;
  canShowResult: boolean;
  form: NestingFormState;
  handleRunJob: () => Promise<void>;
  job: JobResponse | null;
  jobError: string | null;
  jobLoading: boolean;
  nestingStatus: string;
  polling: boolean;
  previewPolygons: PolygonPayload[];
  result: NestingResultResponse | null;
  setActiveSheetIndex: (value: number) => void;
  setWorkflowStep: (value: WorkflowStep) => void;
  groupedOrders: OrderGroupSummary[];
  t: Translate;
};

function ScreenThree({
  activeSheetIndex,
  canShowResult,
  form,
  handleRunJob,
  job,
  jobError,
  jobLoading,
  nestingStatus,
  polling,
  previewPolygons,
  result,
  setActiveSheetIndex,
  setWorkflowStep,
  groupedOrders,
  t,
}: ScreenThreeProps) {
  const currentYield = result?.yield_ratio ?? result?.yield ?? result?.yield_value ?? 0;
  const currentScrap = result?.scrap_ratio ?? (result?.total_sheet_area ? result.scrap_area / result.total_sheet_area : 0);
  const totalPlaced = result?.total_parts_placed ?? result?.parts_placed ?? 0;
  const currentArtifacts = result?.artifacts?.length ? result.artifacts : job?.artifacts ?? [];
  const runButtonLabel = result ? t("common.repeat") : t("screen3.runNesting");
  const improvementLabel =
    typeof result?.improvement_percent === "number" && result.improvement_percent !== 0
      ? `${result.improvement_percent > 0 ? "+" : ""}${result.improvement_percent.toFixed(2)}%`
      : t("screen3.noPriorRun");

  return (
    <div className="grid gap-6 xl:grid-cols-[350px_minmax(0,1fr)_360px]">
      <aside className="space-y-6">
        <Panel title={t("screen3.runControl")} subtitle={t("screen3.runControlSubtitle")}>
          <div className="space-y-3">
            <SummaryCard label={t("screen3.material")} value={form.materialName || t("common.notSet")} />
            <SummaryCard label={t("screen3.mode")} value={form.nestingMode === "fill_sheet" ? t("nesting.fillSheet") : t("nesting.batchQuantity")} />
            <SummaryCard label={t("screen3.sheetSize")} value={`${form.sheetWidth} x ${form.sheetHeight} ${form.sheetUnits}`} />
            <SummaryCard label={t("screen3.improvement")} value={improvementLabel} />
            <SummaryCard label={t("screen3.backend")} value={result?.engine_backend_used ?? job?.engine_backend_used ?? t("screen3.defaultBackend")} />
          </div>
          <button
            className="mt-4 w-full rounded-2xl bg-[linear-gradient(135deg,var(--brand-primary)_0%,#059669_100%)] px-4 py-3 text-sm font-semibold text-white shadow-[0_14px_28px_rgba(16,185,129,0.22)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:shadow-none"
            disabled={jobLoading || polling}
            onClick={() => void handleRunJob()}
            type="button"
          >
            {jobLoading ? t("screen3.creatingJob") : runButtonLabel}
          </button>
          <div className="mt-3 flex gap-3">
            <button
              className="flex-1 rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent"
              onClick={() => setWorkflowStep(2)}
              type="button"
            >
              {t("common.back")}
            </button>
            <button
              className="flex-1 rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent"
              onClick={() => void handleRunJob()}
              type="button"
            >
              {t("common.repeat")}
            </button>
          </div>
          <StatusMessage message={nestingStatus} tone={jobError ? "error" : "neutral"} />
        </Panel>

        <JobStatusPanel disconnected={false} error={jobError} job={job} polling={polling} t={t} />

        <Panel title={t("screen3.artifacts")} subtitle={t("screen3.artifactsSubtitle")}>
          <div className="space-y-3">
            {currentArtifacts.length > 0 ? (
              currentArtifacts.map((artifact) => (
                <ArtifactRow
                  key={artifact.kind}
                  label={t(`artifacts.${artifact.kind}`)}
                  status={artifact.status}
                  text={artifact.message}
                  href={artifact.status === "available" ? artifact.url ?? undefined : undefined}
                  t={t}
                />
              ))
            ) : (
              <>
                <ArtifactRow label={t("artifacts.dxf")} status="unavailable" text={t("artifacts.dxfUnavailable")} t={t} />
                <ArtifactRow label={t("artifacts.pdf")} status="unavailable" text={t("artifacts.pdfUnavailable")} t={t} />
                <ArtifactRow
                  label={t("artifacts.json")}
                  status={job?.artifact_url ? "available" : "unavailable"}
                  text={job?.artifact_url ? t("artifacts.jsonAvailable") : t("artifacts.jsonUnavailable")}
                  href={job?.artifact_url ?? undefined}
                  t={t}
                />
              </>
            )}
          </div>
        </Panel>

        <Panel title={t("screen3.batchOverview")} subtitle={t("screen3.batchOverviewSubtitle")}>
          <div className="space-y-3">
            <SummaryCard label={t("nesting.batchId")} value={result?.batch?.batch_id || form.batchId || "batch-current"} />
            <SummaryCard label={t("nesting.batchName")} value={result?.batch?.batch_name || form.batchName || t("common.notSet")} />
            <SummaryCard
              label={t("metrics.batchOrders")}
              value={`${result?.batch?.orders.length ?? groupedOrders.length}`}
            />
          </div>
          {(result?.batch?.orders.length ?? groupedOrders.length) > 0 ? (
            <div className="mt-4 space-y-2">
              {(result?.batch?.orders ?? groupedOrders.map((order) => ({
                order_id: order.orderId,
                order_name: order.orderName || null,
                priority: order.priority ? Number(order.priority) : null,
                part_ids: [],
              }))).map((order) => (
                <div key={order.order_id} className="rounded-xl border border-[color:var(--border)] bg-white/[0.03] px-3 py-3 text-sm text-slate-300">
                  <div className="font-semibold text-slate-100">{order.order_name || order.order_id}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {t("common.id")}: {order.order_id} | {t("upload.priority")}: {order.priority ?? t("common.notSet")}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 text-sm text-slate-400">{t("screen3.batchOverviewEmpty")}</div>
          )}
        </Panel>
      </aside>

      <main>
        <LayoutViewer
          activeSheetIndex={activeSheetIndex}
          canShowResult={canShowResult}
          debug={result?.debug ?? null}
          layouts={result?.layouts ?? []}
          onSheetChange={setActiveSheetIndex}
          previewPolygons={previewPolygons}
          t={t}
        />
      </main>

      <aside className="space-y-6">
        <MetricsPanel result={canShowResult ? result : null} t={t} />
        <Panel title={t("screen3.runSummary")} subtitle={t("screen3.runSummarySubtitle")}>
          <div className="space-y-3">
            <SummaryCard label={t("screen3.runNumber")} value={`${result?.run_number ?? job?.run_number ?? 0}`} />
            <SummaryCard label={t("screen3.computeTime")} value={result?.compute_time_sec ? `${result.compute_time_sec.toFixed(2)}s` : t("screen3.waitingForResult")} />
            <SummaryCard label={t("metrics.yield")} value={result ? formatPercent(currentYield) : t("screen3.waitingForResult")} />
            <SummaryCard label={t("metrics.scrap")} value={result ? formatPercent(currentScrap) : t("screen3.waitingForResult")} />
            <SummaryCard label={t("screen3.totalPartsPlaced")} value={result ? `${totalPlaced}` : t("screen3.waitingForResult")} />
            <SummaryCard label={t("metrics.usedArea")} value={result ? formatNumber(result.used_area) : t("screen3.waitingForResult")} />
          </div>
          {result?.engine_fallback_reason ? (
            <div className="mt-3 rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              {t("screen3.engineFallback")}: {result.engine_fallback_reason}
            </div>
          ) : null}
        </Panel>
      </aside>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3 text-sm text-slate-300">
      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</div>
      <div className="mt-1 text-base font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function ArtifactRow({
  label,
  text,
  status,
  href,
  t,
}: {
  label: string;
  text: string;
  status: "available" | "processing" | "failed" | "unavailable";
  href?: string;
  t: Translate;
}) {
  const theme =
    status === "available"
      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
      : status === "processing"
        ? "border-sky-400/30 bg-sky-500/10 text-sky-100"
        : status === "failed"
          ? "border-rose-400/30 bg-rose-500/10 text-rose-100"
          : "border-[color:var(--border)] bg-black/15 text-slate-300";
  const badgeTone =
    status === "available"
      ? "text-emerald-200"
      : status === "processing"
        ? "text-sky-200"
        : status === "failed"
          ? "text-rose-200"
          : "text-slate-500";
  const body = (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${theme}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold">{label}</div>
        <div className={`text-[11px] uppercase tracking-[0.16em] ${badgeTone}`}>{t(`artifacts.status.${status}`)}</div>
      </div>
      <div className="mt-1 text-xs">{text}</div>
    </div>
  );

  if (href) {
    return (
      <a href={href} rel="noreferrer" target="_blank">
        {body}
      </a>
    );
  }

  return body;
}
