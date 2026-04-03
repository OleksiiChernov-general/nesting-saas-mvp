import type {
  CleanGeometryResponse,
  DXFAuditPayload,
  DebugBBox,
  DebugPlacement,
  DebugScaleInfo,
  DebugSheet,
  HealthResponse,
  ImportResponse,
  InvalidShape,
  JobResponse,
  NestingResultResponse,
  PlacementResponse,
  Point,
  PolygonPayload,
  SheetLayoutResponse,
  ArtifactDescriptor,
  EconomicMetrics,
  MaterialRecord,
  OffcutPiece,
  OffcutSummary,
  OffcutSheetSummary,
  LeftoverSummary,
  BatchInput,
  BatchOrder,
} from "../types/api";
import { API_BASE_URL } from "./config";

function toNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function toStringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function normalizePoint(value: unknown): Point | null {
  if (!value || typeof value !== "object") return null;
  const point = value as Record<string, unknown>;
  const x = toNumber(point.x, Number.NaN);
  const y = toNumber(point.y, Number.NaN);
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
}

export function normalizePolygon(value: unknown): PolygonPayload | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const points = Array.isArray(record.points) ? record.points.map(normalizePoint).filter((item): item is Point => item !== null) : [];
  if (points.length < 3) return null;
  const first = points[0];
  const last = points[points.length - 1];
  const closed = first.x === last.x && first.y === last.y ? points : [...points, first];
  return closed.length >= 4 ? { points: closed } : null;
}

function normalizeInvalidShapes(value: unknown): InvalidShape[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const record = item as Record<string, unknown>;
    return {
      source: toStringValue(record?.source, `shape-${index + 1}`),
      reason: toStringValue(record?.reason, "Invalid geometry"),
    };
  });
}

function normalizeBoundsPayload(value: unknown) {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    min_x: toNumber(record.min_x),
    min_y: toNumber(record.min_y),
    max_x: toNumber(record.max_x),
    max_y: toNumber(record.max_y),
    width: toNumber(record.width),
    height: toNumber(record.height),
  };
}

function normalizeBatchOrder(value: unknown, index: number): BatchOrder {
  const record = value as Record<string, unknown> | null;
  return {
    order_id: toStringValue(record?.order_id, `order-${index + 1}`),
    order_name: typeof record?.order_name === "string" ? record.order_name : null,
    priority: typeof record?.priority === "number" ? record.priority : null,
    part_ids: Array.isArray(record?.part_ids) ? record.part_ids.map((item, partIndex) => toStringValue(item, `part-${partIndex + 1}`)) : [],
  };
}

function normalizeBatchInput(value: unknown): BatchInput | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    batch_id: typeof record.batch_id === "string" ? record.batch_id : null,
    batch_name: typeof record.batch_name === "string" ? record.batch_name : null,
    orders: Array.isArray(record.orders) ? record.orders.map((item, index) => normalizeBatchOrder(item, index)) : [],
  };
}

function normalizeArtifactDescriptor(value: unknown, index: number): ArtifactDescriptor {
  const record = value as Record<string, unknown> | null;
  const kind = toStringValue(record?.kind, index === 0 ? "json" : index === 1 ? "dxf" : "pdf");
  const url =
    typeof record?.url === "string"
      ? record.url.startsWith("/")
        ? `${API_BASE_URL}${record.url}`
        : record.url
      : null;
  return {
    kind: kind === "dxf" || kind === "pdf" ? kind : "json",
    label: toStringValue(record?.label, kind.toUpperCase()),
    status:
      record?.status === "available" ||
      record?.status === "processing" ||
      record?.status === "failed" ||
      record?.status === "unavailable"
        ? record.status
        : "unavailable",
    url,
    message: toStringValue(record?.message, "Artifact state is unavailable."),
    content_type: typeof record?.content_type === "string" ? record.content_type : null,
    filename: typeof record?.filename === "string" ? record.filename : null,
  };
}

function normalizeEconomicMetrics(value: unknown): EconomicMetrics | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    status: record.status === "available" ? "available" : "placeholder",
    material_cost: typeof record.material_cost === "number" ? record.material_cost : null,
    used_material_cost: typeof record.used_material_cost === "number" ? record.used_material_cost : null,
    waste_cost: typeof record.waste_cost === "number" ? record.waste_cost : null,
    savings_percent: typeof record.savings_percent === "number" ? record.savings_percent : null,
    currency: typeof record.currency === "string" ? record.currency : null,
    cost_basis: typeof record.cost_basis === "string" ? record.cost_basis : null,
    material_cost_estimated: record.material_cost_estimated === true,
    used_material_cost_estimated: record.used_material_cost_estimated === true,
    waste_cost_estimated: record.waste_cost_estimated === true,
    savings_percent_estimated: record.savings_percent_estimated === true,
    message: toStringValue(record.message, "Economic metrics are unavailable."),
  };
}

function normalizeOffcutPiece(value: unknown): OffcutPiece | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const bounds = normalizeBoundsPayload(record.bounds);
  if (!bounds) return null;
  return {
    sheet_id: toStringValue(record.sheet_id, "sheet-1"),
    instance: toNumber(record.instance, 1),
    area: toNumber(record.area),
    approx_shape:
      record.approx_shape === "bounding_box" || record.approx_shape === "sheet_remainder" ? record.approx_shape : "rectangle",
    bounds,
    reusable: record.reusable !== false,
    approximation: record.approximation !== false,
    source: toStringValue(record.source, "unknown"),
  };
}

function normalizeOffcutSheetSummary(value: unknown): OffcutSheetSummary | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    sheet_id: toStringValue(record.sheet_id, "sheet-1"),
    instance: toNumber(record.instance, 1),
    sheet_area: toNumber(record.sheet_area),
    used_area: toNumber(record.used_area),
    scrap_area: toNumber(record.scrap_area),
    reusable_leftover_area: toNumber(record.reusable_leftover_area),
    estimated_scrap_area: toNumber(record.estimated_scrap_area),
    reusable_piece_count: toNumber(record.reusable_piece_count),
    approximation: record.approximation !== false,
    approximation_method: toStringValue(record.approximation_method, "unknown"),
    message: toStringValue(record.message, "Offcut summary is unavailable."),
  };
}

function normalizeLeftoverSummary(value: unknown): LeftoverSummary | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    sheet_id: toStringValue(record.sheet_id, "sheet-1"),
    instance: toNumber(record.instance, 1),
    width: toNumber(record.width),
    height: toNumber(record.height),
    area: toNumber(record.area),
    approximate: record.approximate !== false,
    source: typeof record.source === "string" ? record.source : null,
  };
}

function normalizeOffcutSummary(value: unknown): OffcutSummary | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    total_leftover_area: toNumber(record.total_leftover_area),
    reusable_leftover_area: toNumber(record.reusable_leftover_area),
    reusable_area_estimate:
      typeof record.reusable_area_estimate === "number" ? record.reusable_area_estimate : toNumber(record.reusable_leftover_area),
    estimated_scrap_area: toNumber(record.estimated_scrap_area),
    reusable_piece_count: toNumber(record.reusable_piece_count),
    approximation: record.approximation !== false,
    approximation_method: toStringValue(record.approximation_method, "unknown"),
    message: toStringValue(record.message, "Offcut summary is unavailable."),
    leftover_summaries: Array.isArray(record.leftover_summaries)
      ? record.leftover_summaries.map(normalizeLeftoverSummary).filter((item): item is LeftoverSummary => item !== null)
      : [],
    sheets: Array.isArray(record.sheets)
      ? record.sheets.map(normalizeOffcutSheetSummary).filter((item): item is OffcutSheetSummary => item !== null)
      : [],
  };
}

function normalizeGeometryStats(value: unknown) {
  const record = value as Record<string, unknown> | null;
  return {
    polygon_count: toNumber(record?.polygon_count),
    total_area: toNumber(record?.total_area),
    min_width: typeof record?.min_width === "number" ? record.min_width : null,
    median_width: typeof record?.median_width === "number" ? record.median_width : null,
    max_width: typeof record?.max_width === "number" ? record.max_width : null,
    min_height: typeof record?.min_height === "number" ? record.min_height : null,
    median_height: typeof record?.median_height === "number" ? record.median_height : null,
    max_height: typeof record?.max_height === "number" ? record.max_height : null,
    min_area: typeof record?.min_area === "number" ? record.min_area : null,
    median_area: typeof record?.median_area === "number" ? record.median_area : null,
    max_area: typeof record?.max_area === "number" ? record.max_area : null,
    max_extent: typeof record?.max_extent === "number" ? record.max_extent : null,
  };
}

function normalizeDXFAudit(value: unknown): DXFAuditPayload | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    units_code: typeof record.units_code === "number" ? record.units_code : null,
    detected_units: typeof record.detected_units === "string" ? record.detected_units : null,
    measurement_system: typeof record.measurement_system === "string" ? record.measurement_system : null,
    source_bounds: normalizeBoundsPayload(record.source_bounds),
    geometry_stats: normalizeGeometryStats(record.geometry_stats),
    warnings: Array.isArray(record.warnings)
      ? record.warnings.map((item, index) => toStringValue(item, `warning-${index + 1}`))
      : [],
  };
}

export function normalizeHealthResponse(value: unknown): HealthResponse {
  const record = value as Record<string, unknown> | null;
  return { status: toStringValue(record?.status, "unavailable") };
}

export function normalizeImportResponse(value: unknown, fallbackFilename: string): ImportResponse {
  const record = value as Record<string, unknown> | null;
  return {
    import_id: toStringValue(record?.import_id),
    filename: toStringValue(record?.filename, fallbackFilename),
    polygons: Array.isArray(record?.polygons)
      ? record.polygons.map(normalizePolygon).filter((item): item is PolygonPayload => item !== null)
      : [],
    invalid_shapes: normalizeInvalidShapes(record?.invalid_shapes),
    audit: normalizeDXFAudit(record?.audit),
  };
}

export function normalizeCleanupResponse(value: unknown): CleanGeometryResponse {
  const record = value as Record<string, unknown> | null;
  return {
    polygons: Array.isArray(record?.polygons)
      ? record.polygons.map(normalizePolygon).filter((item): item is PolygonPayload => item !== null)
      : [],
    removed: toNumber(record?.removed),
    invalid_shapes: normalizeInvalidShapes(record?.invalid_shapes),
  };
}

export function normalizeMaterialRecord(value: unknown, index = 0): MaterialRecord {
  const record = value as Record<string, unknown> | null;
  return {
    material_id: toStringValue(record?.material_id, `material-${index + 1}`),
    name: toStringValue(record?.name, `Material ${index + 1}`),
    thickness: toNumber(record?.thickness, 1),
    sheet_width: toNumber(record?.sheet_width, 100),
    sheet_height: toNumber(record?.sheet_height, 100),
    units: record?.units === "in" ? "in" : "mm",
    kerf: toNumber(record?.kerf, 0),
    cost_per_sheet: typeof record?.cost_per_sheet === "number" ? record.cost_per_sheet : null,
    currency: typeof record?.currency === "string" ? record.currency : null,
    notes: typeof record?.notes === "string" ? record.notes : null,
    created_at: toStringValue(record?.created_at),
    updated_at: toStringValue(record?.updated_at),
  };
}

export function normalizeJobResponse(value: unknown): JobResponse {
  const record = value as Record<string, unknown> | null;
  const state = toStringValue(record?.state, "FAILED");
  const artifactUrl =
    typeof record?.artifact_url === "string"
      ? record.artifact_url.startsWith("/")
        ? `${API_BASE_URL}${record.artifact_url}`
        : record.artifact_url
      : null;
  return {
    id: toStringValue(record?.id),
    state: ["CREATED", "QUEUED", "RUNNING", "PARTIAL", "SUCCEEDED", "FAILED", "CANCELLED"].includes(state)
      ? (state as JobResponse["state"])
      : "FAILED",
    progress: toNumber(record?.progress),
    status_message: typeof record?.status_message === "string" ? record.status_message : null,
    error: typeof record?.error === "string" ? record.error : null,
    mode:
      record?.mode === "fill_sheet" || record?.mode === "batch_quantity"
        ? (record.mode as JobResponse["mode"])
        : null,
    summary:
      record?.summary && typeof record.summary === "object"
        ? {
            total_parts: toNumber((record.summary as Record<string, unknown>).total_parts),
          }
        : null,
    parts: Array.isArray(record?.parts)
      ? record.parts.map((item, index) => {
          const part = item as Record<string, unknown> | null;
          return {
            part_id: toStringValue(part?.part_id, `part-${index + 1}`),
            filename: typeof part?.filename === "string" ? part.filename : null,
            requested_quantity: Math.max(1, toNumber(part?.requested_quantity, 1)),
            placed_quantity: toNumber(part?.placed_quantity),
            remaining_quantity: Math.max(0, toNumber(part?.remaining_quantity)),
            enabled: typeof part?.enabled === "boolean" ? part.enabled : true,
            area_contribution: toNumber(part?.area_contribution),
            order_id: typeof part?.order_id === "string" ? part.order_id : null,
            order_name: typeof part?.order_name === "string" ? part.order_name : null,
            priority: typeof part?.priority === "number" ? part.priority : null,
          };
        })
      : [],
    batch: normalizeBatchInput(record?.batch),
    artifact_url: artifactUrl,
    artifacts: Array.isArray(record?.artifacts) ? record.artifacts.map((item, index) => normalizeArtifactDescriptor(item, index)) : [],
    created_at: typeof record?.created_at === "string" ? record.created_at : null,
    queued_at: typeof record?.queued_at === "string" ? record.queued_at : null,
    started_at: typeof record?.started_at === "string" ? record.started_at : null,
    heartbeat_at: typeof record?.heartbeat_at === "string" ? record.heartbeat_at : null,
    finished_at: typeof record?.finished_at === "string" ? record.finished_at : null,
    run_number: toNumber(record?.run_number, 1),
    compute_time_sec: toNumber(record?.compute_time_sec),
    current_yield: toNumber(record?.current_yield),
    previous_yield: toNumber(record?.previous_yield),
    best_yield: toNumber(record?.best_yield),
    improvement_percent: toNumber(record?.improvement_percent),
    engine_backend_requested:
      record?.engine_backend_requested === "native" || record?.engine_backend_requested === "python"
        ? record.engine_backend_requested
        : null,
    engine_backend_used:
      record?.engine_backend_used === "native" || record?.engine_backend_used === "python"
        ? record.engine_backend_used
        : null,
    engine_fallback_reason: typeof record?.engine_fallback_reason === "string" ? record.engine_fallback_reason : null,
  };
}

function normalizePlacement(value: unknown, index: number): PlacementResponse | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const polygon = normalizePolygon(record.polygon);
  if (!polygon) return null;
  return {
    part_id: toStringValue(record.part_id, `part-${index + 1}`),
    sheet_id: toStringValue(record.sheet_id, "sheet"),
    instance: toNumber(record.instance, 1),
    rotation: toNumber(record.rotation, 0),
    x: toNumber(record.x),
    y: toNumber(record.y),
    width: toNumber(record.width),
    height: toNumber(record.height),
    polygon,
    order_id: typeof record.order_id === "string" ? record.order_id : null,
    order_name: typeof record.order_name === "string" ? record.order_name : null,
    priority: typeof record.priority === "number" ? record.priority : null,
  };
}

function normalizeLayout(value: unknown, index: number): SheetLayoutResponse | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const placements = Array.isArray(record.placements)
    ? record.placements.map((item, placementIndex) => normalizePlacement(item, placementIndex)).filter((item): item is PlacementResponse => item !== null)
    : [];
  return {
    sheet_id: toStringValue(record.sheet_id, `sheet-${index + 1}`),
    instance: toNumber(record.instance, index + 1),
    width: toNumber(record.width, 1),
    height: toNumber(record.height, 1),
    placements,
    used_area: toNumber(record.used_area),
    scrap_area: toNumber(record.scrap_area),
  };
}

function normalizeDebugBBox(value: unknown): DebugBBox | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    min_x: toNumber(record.min_x),
    min_y: toNumber(record.min_y),
    max_x: toNumber(record.max_x),
    max_y: toNumber(record.max_y),
    width: toNumber(record.width),
    height: toNumber(record.height),
  };
}

function normalizeDebugSheet(value: unknown, index: number): DebugSheet | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    sheet_id: toStringValue(record.sheet_id, `sheet-${index + 1}`),
    instance: toNumber(record.instance, index + 1),
    width: toNumber(record.width),
    height: toNumber(record.height),
    area: toNumber(record.area),
  };
}

function normalizeDebugPlacement(value: unknown, index: number): DebugPlacement | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const bbox = normalizeDebugBBox(record.bbox);
  if (!bbox) return null;
  return {
    placement_id: toStringValue(record.placement_id, `placement-${index + 1}`),
    part_id: toStringValue(record.part_id, `part-${index + 1}`),
    sheet_id: toStringValue(record.sheet_id, "sheet-1"),
    instance: toNumber(record.instance, 1),
    area: toNumber(record.area),
    bbox,
    valid: Boolean(record.valid),
    within_sheet: Boolean(record.within_sheet),
  };
}

function normalizeDebugScaleInfo(value: unknown): DebugScaleInfo {
  const record = value as Record<string, unknown> | null;
  return {
    placement_bounds: normalizeDebugBBox(record?.placement_bounds),
    max_extent: toNumber(record?.max_extent),
    sheet_max_extent: toNumber(record?.sheet_max_extent),
    extent_ratio: toNumber(record?.extent_ratio),
    cluster_flagged: Boolean(record?.cluster_flagged),
  };
}

export function normalizeResultResponse(value: unknown): NestingResultResponse {
  const record = value as Record<string, unknown> | null;
  const yieldValue = typeof record?.yield === "number" ? record.yield : toNumber(record?.yield_value);
  const scrapRatio =
    typeof record?.scrap_ratio === "number"
      ? record.scrap_ratio
      : toNumber(record?.total_sheet_area) > 0
        ? toNumber(record?.scrap_area) / toNumber(record?.total_sheet_area)
        : 0;
  return {
    status:
      record?.status === "SUCCEEDED" || record?.status === "PARTIAL" || record?.status === "FAILED"
        ? (record.status as NestingResultResponse["status"])
        : "FAILED",
    mode:
      record?.mode === "fill_sheet" || record?.mode === "batch_quantity"
        ? (record.mode as NestingResultResponse["mode"])
        : "batch_quantity",
    summary:
      record?.summary && typeof record.summary === "object"
        ? {
            total_parts: toNumber((record.summary as Record<string, unknown>).total_parts),
          }
        : {
            total_parts: Array.isArray(record?.parts)
              ? record.parts.length
                : 0,
          },
    yield: yieldValue,
    yield_value: yieldValue,
    yield_ratio: typeof record?.yield_ratio === "number" ? record.yield_ratio : yieldValue,
    scrap_ratio: scrapRatio,
    scrap_area: toNumber(record?.scrap_area),
    used_area: toNumber(record?.used_area),
    total_sheet_area: toNumber(record?.total_sheet_area),
    parts_placed: toNumber(record?.parts_placed || record?.total_parts_placed),
    total_parts_placed: toNumber(record?.total_parts_placed || record?.parts_placed),
    layouts_used: toNumber(record?.layouts_used),
    layouts: Array.isArray(record?.layouts)
      ? record.layouts.map((item, index) => normalizeLayout(item, index)).filter((item): item is SheetLayoutResponse => item !== null)
      : [],
    parts: Array.isArray(record?.parts)
      ? record.parts.map((item, index) => {
          const part = item as Record<string, unknown> | null;
          return {
            part_id: toStringValue(part?.part_id, `part-${index + 1}`),
            filename: typeof part?.filename === "string" ? part.filename : null,
            requested_quantity: Math.max(1, toNumber(part?.requested_quantity, 1)),
            placed_quantity: toNumber(part?.placed_quantity),
            remaining_quantity: Math.max(0, toNumber(part?.remaining_quantity)),
            enabled: typeof part?.enabled === "boolean" ? part.enabled : true,
            area_contribution: toNumber(part?.area_contribution),
            order_id: typeof part?.order_id === "string" ? part.order_id : null,
            order_name: typeof part?.order_name === "string" ? part.order_name : null,
            priority: typeof part?.priority === "number" ? part.priority : null,
          };
        })
        : [],
    batch: normalizeBatchInput(record?.batch),
    artifacts: Array.isArray(record?.artifacts) ? record.artifacts.map((item, index) => normalizeArtifactDescriptor(item, index)) : [],
    economics: normalizeEconomicMetrics(record?.economics),
    offcuts: Array.isArray(record?.offcuts)
      ? record.offcuts.map(normalizeOffcutPiece).filter((item): item is OffcutPiece => item !== null)
      : [],
    offcut_summary: normalizeOffcutSummary(record?.offcut_summary),
    unplaced_parts: Array.isArray(record?.unplaced_parts)
      ? record.unplaced_parts.map((item, index) => toStringValue(item, `part-${index + 1}`))
      : [],
    warnings: Array.isArray(record?.warnings)
      ? record.warnings.map((item, index) => toStringValue(item, `warning-${index + 1}`))
      : [],
    job_id: typeof record?.job_id === "string" ? record.job_id : null,
    run_number: toNumber(record?.run_number, 1),
    compute_time_sec: toNumber(record?.compute_time_sec),
    previous_yield: toNumber(record?.previous_yield),
    best_yield: toNumber(record?.best_yield),
    improvement_percent: toNumber(record?.improvement_percent),
    timed_out: Boolean(record?.timed_out),
    optimization_history: Array.isArray(record?.optimization_history)
      ? record.optimization_history.map((item, index) => {
          const entry = item as Record<string, unknown> | null;
          return {
            job_id: toStringValue(entry?.job_id, `job-${index + 1}`),
            run_number: toNumber(entry?.run_number, index + 1),
            status: toStringValue(entry?.status, "FAILED"),
            yield: toNumber(entry?.yield),
            compute_time_sec: toNumber(entry?.compute_time_sec),
            improvement_percent: toNumber(entry?.improvement_percent),
          };
        })
      : [],
    engine_backend_requested:
      record?.engine_backend_requested === "native" || record?.engine_backend_requested === "python"
        ? record.engine_backend_requested
        : null,
    engine_backend_used:
      record?.engine_backend_used === "native" || record?.engine_backend_used === "python"
        ? record.engine_backend_used
        : null,
    engine_fallback_reason: typeof record?.engine_fallback_reason === "string" ? record.engine_fallback_reason : null,
    debug:
      record?.debug && typeof record.debug === "object"
        ? {
            sheet: normalizeDebugSheet((record.debug as Record<string, unknown>).sheet, 0),
            sheets: Array.isArray((record.debug as Record<string, unknown>).sheets)
              ? ((record.debug as Record<string, unknown>).sheets as unknown[])
                  .map((item, index) => normalizeDebugSheet(item, index))
                  .filter((item): item is DebugSheet => item !== null)
              : [],
            placements: Array.isArray((record.debug as Record<string, unknown>).placements)
              ? ((record.debug as Record<string, unknown>).placements as unknown[])
                  .map((item, index) => normalizeDebugPlacement(item, index))
                  .filter((item): item is DebugPlacement => item !== null)
              : [],
            total_used_area: toNumber((record.debug as Record<string, unknown>).total_used_area),
            total_scrap_area: toNumber((record.debug as Record<string, unknown>).total_scrap_area),
            scale_info: normalizeDebugScaleInfo((record.debug as Record<string, unknown>).scale_info),
            warnings: Array.isArray((record.debug as Record<string, unknown>).warnings)
              ? ((record.debug as Record<string, unknown>).warnings as unknown[]).map((item, index) => toStringValue(item, `warning-${index + 1}`))
              : [],
          }
        : null,
  };
}
