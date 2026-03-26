import type {
  CleanGeometryResponse,
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
    state: ["CREATED", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"].includes(state)
      ? (state as JobResponse["state"])
      : "FAILED",
    progress: toNumber(record?.progress),
    status_message: typeof record?.status_message === "string" ? record.status_message : null,
    error: typeof record?.error === "string" ? record.error : null,
    artifact_url: artifactUrl,
    created_at: typeof record?.created_at === "string" ? record.created_at : null,
    queued_at: typeof record?.queued_at === "string" ? record.queued_at : null,
    started_at: typeof record?.started_at === "string" ? record.started_at : null,
    heartbeat_at: typeof record?.heartbeat_at === "string" ? record.heartbeat_at : null,
    finished_at: typeof record?.finished_at === "string" ? record.finished_at : null,
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
    yield: yieldValue,
    yield_value: yieldValue,
    yield_ratio: typeof record?.yield_ratio === "number" ? record.yield_ratio : yieldValue,
    scrap_ratio: scrapRatio,
    scrap_area: toNumber(record?.scrap_area),
    used_area: toNumber(record?.used_area),
    total_sheet_area: toNumber(record?.total_sheet_area),
    parts_placed: toNumber(record?.parts_placed),
    layouts_used: toNumber(record?.layouts_used),
    layouts: Array.isArray(record?.layouts)
      ? record.layouts.map((item, index) => normalizeLayout(item, index)).filter((item): item is SheetLayoutResponse => item !== null)
      : [],
    unplaced_parts: Array.isArray(record?.unplaced_parts)
      ? record.unplaced_parts.map((item, index) => toStringValue(item, `part-${index + 1}`))
      : [],
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
