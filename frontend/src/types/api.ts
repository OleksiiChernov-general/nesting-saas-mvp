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

export type ImportResponse = {
  import_id: string;
  filename: string;
  polygons: PolygonPayload[];
  invalid_shapes: InvalidShape[];
};

export type CleanGeometryResponse = {
  polygons: PolygonPayload[];
  removed: number;
  invalid_shapes: InvalidShape[];
};

export type PartInput = {
  part_id: string;
  quantity: number;
  polygon: PolygonPayload;
};

export type SheetInput = {
  sheet_id: string;
  width: number;
  height: number;
  quantity: number;
};

export type NestingJobCreateRequest = {
  parts: PartInput[];
  sheets: SheetInput[];
  params: {
    gap: number;
    rotation: Array<0 | 180>;
    objective: string;
  };
};

export type JobResponse = {
  id: string;
  state: "CREATED" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  progress: number;
  status_message?: string | null;
  error?: string | null;
  artifact_url?: string | null;
  created_at?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  finished_at?: string | null;
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

export type NestingResultResponse = {
  yield?: number;
  yield_value?: number;
  yield_ratio?: number;
  scrap_ratio?: number;
  scrap_area: number;
  used_area: number;
  total_sheet_area: number;
  parts_placed?: number;
  layouts_used?: number;
  layouts: SheetLayoutResponse[];
  unplaced_parts: string[];
};
