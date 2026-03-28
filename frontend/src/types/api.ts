export type HealthResponse = {
  status?: string;
};

export type Point = {
  x: number;
  y: number;
};

export type PolygonPayload = {
  points: Point[];
};

export type InvalidShape = {
  source: string;
  reason: string;
};

export type BoundsPayload = {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
  width: number;
  height: number;
};

export type GeometryStatsPayload = {
  polygon_count: number;
  total_area: number;
  min_width?: number | null;
  median_width?: number | null;
  max_width?: number | null;
  min_height?: number | null;
  median_height?: number | null;
  max_height?: number | null;
  min_area?: number | null;
  median_area?: number | null;
  max_area?: number | null;
  max_extent?: number | null;
};

export type DXFAuditPayload = {
  units_code?: number | null;
  detected_units?: string | null;
  measurement_system?: string | null;
  source_bounds?: BoundsPayload | null;
  geometry_stats: GeometryStatsPayload;
  warnings: string[];
};

export type ImportResponse = {
  import_id: string;
  filename: string;
  polygons: PolygonPayload[];
  invalid_shapes: InvalidShape[];
  audit?: DXFAuditPayload | null;
};

export type CleanGeometryResponse = {
  polygons: PolygonPayload[];
  removed: number;
  invalid_shapes: InvalidShape[];
};

export type PartInput = {
  part_id: string;
  filename?: string | null;
  quantity?: number;
  enabled?: boolean;
  fill_only?: boolean;
  polygon: PolygonPayload;
};

export type SheetInput = {
  sheet_id?: string;
  width: number;
  height: number;
  quantity?: number;
  units?: string;
};

export type NestingJobCreateRequest = {
  mode: "fill_sheet" | "batch_quantity";
  parts: PartInput[];
  sheet: SheetInput;
  sheets?: SheetInput[];
  previous_job_id?: string | null;
  params: {
    gap: number;
    rotation: Array<0 | 90 | 180 | 270>;
    objective: string;
    debug?: boolean;
    source_units?: string | null;
    source_max_extent?: number | null;
  };
};

export type JobResponse = {
  id: string;
  state: "CREATED" | "QUEUED" | "RUNNING" | "PARTIAL" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  progress: number;
  status_message?: string | null;
  error?: string | null;
  mode?: "fill_sheet" | "batch_quantity" | null;
  summary?: {
    total_parts: number;
  } | null;
  parts?: Array<{
    part_id: string;
    filename?: string | null;
    requested_quantity: number;
    placed_quantity: number;
    remaining_quantity: number;
    enabled?: boolean;
    area_contribution: number;
  }>;
  artifact_url?: string | null;
  created_at?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  finished_at?: string | null;
  run_number?: number;
  compute_time_sec?: number;
  current_yield?: number;
  previous_yield?: number;
  best_yield?: number;
  improvement_percent?: number;
};

export type PlacementResponse = {
  part_id: string;
  sheet_id: string;
  instance: number;
  rotation: number;
  x: number;
  y: number;
  width: number;
  height: number;
  polygon: PolygonPayload;
};

export type SheetLayoutResponse = {
  sheet_id: string;
  instance: number;
  width: number;
  height: number;
  placements: PlacementResponse[];
  used_area: number;
  scrap_area: number;
};

export type DebugBBox = {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
  width: number;
  height: number;
};

export type DebugSheet = {
  sheet_id: string;
  instance: number;
  width: number;
  height: number;
  area: number;
};

export type DebugPlacement = {
  placement_id: string;
  part_id: string;
  sheet_id: string;
  instance: number;
  area: number;
  bbox: DebugBBox;
  valid: boolean;
  within_sheet: boolean;
};

export type DebugScaleInfo = {
  placement_bounds?: DebugBBox | null;
  max_extent: number;
  sheet_max_extent: number;
  extent_ratio: number;
  cluster_flagged: boolean;
};

export type NestingDebugResponse = {
  sheet?: DebugSheet | null;
  sheets: DebugSheet[];
  placements: DebugPlacement[];
  total_used_area: number;
  total_scrap_area: number;
  scale_info: DebugScaleInfo;
  warnings: string[];
};

export type NestingResultResponse = {
  status?: "SUCCEEDED" | "PARTIAL" | "FAILED";
  mode?: "fill_sheet" | "batch_quantity";
  summary: {
    total_parts: number;
  };
  yield?: number;
  yield_value?: number;
  yield_ratio?: number;
  scrap_ratio?: number;
  scrap_area: number;
  used_area: number;
  total_sheet_area: number;
  parts_placed?: number;
  total_parts_placed?: number;
  layouts_used?: number;
  layouts: SheetLayoutResponse[];
  parts: Array<{
    part_id: string;
    filename?: string | null;
    requested_quantity: number;
    placed_quantity: number;
    remaining_quantity: number;
    enabled?: boolean;
    area_contribution: number;
  }>;
  unplaced_parts: string[];
  warnings?: string[];
  debug?: NestingDebugResponse | null;
  job_id?: string | null;
  run_number?: number;
  compute_time_sec?: number;
  previous_yield?: number;
  best_yield?: number;
  improvement_percent?: number;
  timed_out?: boolean;
  optimization_history?: Array<{
    job_id: string;
    run_number: number;
    status: string;
    yield: number;
    compute_time_sec: number;
    improvement_percent: number;
  }>;
};
