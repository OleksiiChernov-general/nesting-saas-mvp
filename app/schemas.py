from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import JobState


RotationAngle = Literal[0, 45, 90, 135, 180, 225, 270, 315]
ArtifactKind = Literal["json", "dxf", "pdf"]
ArtifactStatus = Literal["available", "processing", "failed", "unavailable"]
EconomicMetricsStatus = Literal["available", "placeholder"]
MaterialUnits = Literal["mm", "in"]
OffcutShape = Literal["rectangle", "bounding_box", "sheet_remainder"]


class Point(BaseModel):
    x: float
    y: float


class PolygonPayload(BaseModel):
    points: list[Point]

    @field_validator("points")
    @classmethod
    def validate_polygon(cls, points: list[Point]) -> list[Point]:
        if len(points) < 4:
            raise ValueError("Polygon must contain at least 4 points including the closing point")
        if points[0] != points[-1]:
            raise ValueError("Polygon must be explicitly closed")
        return points


class InvalidShape(BaseModel):
    source: str
    reason: str


class BoundsPayload(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    width: float
    height: float


class GeometryStatsPayload(BaseModel):
    polygon_count: int
    total_area: float
    min_width: float | None = None
    median_width: float | None = None
    max_width: float | None = None
    min_height: float | None = None
    median_height: float | None = None
    max_height: float | None = None
    min_area: float | None = None
    median_area: float | None = None
    max_area: float | None = None
    max_extent: float | None = None


class DXFAuditPayload(BaseModel):
    units_code: int | None = None
    detected_units: str | None = None
    measurement_system: str | None = None
    source_bounds: BoundsPayload | None = None
    geometry_stats: GeometryStatsPayload
    warnings: list[str] = Field(default_factory=list)


class ImportResponse(BaseModel):
    import_id: str
    filename: str
    polygons: list[PolygonPayload]
    invalid_shapes: list[InvalidShape]
    audit: DXFAuditPayload | None = None


class CleanGeometryRequest(BaseModel):
    polygons: list[PolygonPayload]
    tolerance: float = Field(default=0.5, gt=0)


class CleanGeometryResponse(BaseModel):
    polygons: list[PolygonPayload]
    removed: int
    invalid_shapes: list[InvalidShape]


class PartInput(BaseModel):
    part_id: str
    filename: str | None = None
    polygon: PolygonPayload
    quantity: int | None = Field(default=None, ge=1)
    enabled: bool = True
    fill_only: bool = False
    order_id: str | None = None
    order_name: str | None = None
    priority: int | None = Field(default=None, ge=1)

    @field_validator("order_id", "order_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class SheetInput(BaseModel):
    sheet_id: str = "sheet-1"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1)
    units: str = "mm"


class MaterialInput(BaseModel):
    material_id: str | None = None
    name: str = Field(min_length=1)
    thickness: float = Field(gt=0)
    sheet_width: float = Field(gt=0)
    sheet_height: float = Field(gt=0)
    units: MaterialUnits = "mm"
    kerf: float = Field(default=0.0, ge=0)
    cost_per_sheet: float | None = Field(default=None, gt=0)
    currency: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Material name is required")
        return trimmed

    @field_validator("currency", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class MaterialRecord(MaterialInput):
    material_id: str
    created_at: str
    updated_at: str


class NestingParams(BaseModel):
    gap: float = Field(default=0.0, ge=0)
    rotation: list[RotationAngle] = Field(default_factory=lambda: [0, 45, 90, 135, 180, 225, 270, 315])
    objective: str = "maximize_yield"
    debug: bool = False
    source_units: str | None = None
    source_max_extent: float | None = Field(default=None, gt=0)


class BatchOrderInput(BaseModel):
    order_id: str = Field(min_length=1)
    order_name: str | None = None
    priority: int | None = Field(default=None, ge=1)
    part_ids: list[str] = Field(default_factory=list)

    @field_validator("order_id", "order_name")
    @classmethod
    def normalize_batch_order_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class BatchInput(BaseModel):
    batch_id: str | None = None
    batch_name: str | None = None
    orders: list[BatchOrderInput] = Field(default_factory=list)

    @field_validator("batch_id", "batch_name")
    @classmethod
    def normalize_batch_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class NestingJobCreateRequest(BaseModel):
    mode: Literal["fill_sheet", "batch_quantity"]
    parts: list[PartInput]
    sheet: SheetInput | None = None
    sheets: list[SheetInput] = Field(default_factory=list)
    material: MaterialInput | None = None
    batch: BatchInput | None = None
    params: NestingParams = Field(default_factory=NestingParams)
    previous_job_id: UUID | None = None
    engine_backend: Literal["python", "native"] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_sheet_payload(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        sheet = data.get("sheet")
        sheets = data.get("sheets")
        if sheet and not sheets:
            data["sheets"] = [sheet]
        elif sheets and not sheet and isinstance(sheets, list) and sheets:
            data["sheet"] = sheets[0]
        return data

    @model_validator(mode="after")
    def validate_multi_part_job(self) -> "NestingJobCreateRequest":
        if not self.sheets:
            raise ValueError("sheet is required")
        enabled_parts = [part for part in self.parts if part.enabled]
        if not enabled_parts:
            raise ValueError("At least one enabled part is required")
        if self.mode == "batch_quantity":
            invalid_parts = [part.part_id for part in enabled_parts if part.quantity is None or part.quantity < 1]
            if invalid_parts:
                raise ValueError(f"Batch Quantity mode requires quantity >= 1 for enabled parts: {', '.join(invalid_parts)}")
        explicit_ordered_parts = [part for part in enabled_parts if part.order_id]
        if self.batch and self.batch.orders and explicit_ordered_parts:
            enabled_parts_by_id = {part.part_id: part for part in enabled_parts}
            seen_batch_orders: set[str] = set()
            referenced_parts: set[str] = set()

            for order in self.batch.orders:
                if order.order_id in seen_batch_orders:
                    raise ValueError(f"Batch order ids must be unique: {order.order_id}")
                seen_batch_orders.add(order.order_id)

                if not order.part_ids:
                    matched_ids = [part.part_id for part in enabled_parts if part.order_id == order.order_id]
                    if not matched_ids:
                        raise ValueError(
                            f"Batch order {order.order_id} must reference at least one enabled part by part_ids or matching order_id"
                        )
                    continue

                for part_id in order.part_ids:
                    if part_id in referenced_parts:
                        raise ValueError(f"Part {part_id} cannot belong to multiple batch orders")
                    part = enabled_parts_by_id.get(part_id)
                    if part is None:
                        raise ValueError(f"Batch order {order.order_id} references unknown or disabled part_id: {part_id}")
                    if part.order_id and part.order_id != order.order_id:
                        raise ValueError(
                            f"Batch order {order.order_id} does not match part {part_id} order_id {part.order_id}"
                        )
                    if part.priority is not None and order.priority is not None and part.priority != order.priority:
                        raise ValueError(
                            f"Batch order {order.order_id} priority {order.priority} does not match part {part_id} priority {part.priority}"
                        )
                    referenced_parts.add(part_id)

            missing_batch_orders = sorted({part.order_id for part in explicit_ordered_parts} - seen_batch_orders)
            if missing_batch_orders:
                raise ValueError(
                    "Batch metadata is missing explicit part order ids: " + ", ".join(missing_batch_orders)
                )
        return self


class NestingPartsSummaryResponse(BaseModel):
    total_parts: int


class PartResultResponse(BaseModel):
    part_id: str
    filename: str | None = None
    requested_quantity: int
    placed_quantity: int
    remaining_quantity: int
    enabled: bool = True
    area_contribution: float
    order_id: str | None = None
    order_name: str | None = None
    priority: int | None = None


class ArtifactDescriptorResponse(BaseModel):
    kind: ArtifactKind
    label: str
    status: ArtifactStatus
    url: str | None = None
    message: str
    content_type: str | None = None
    filename: str | None = None


class EconomicMetricsResponse(BaseModel):
    status: EconomicMetricsStatus = "placeholder"
    material_cost: float | None = None
    used_material_cost: float | None = None
    waste_cost: float | None = None
    savings_percent: float | None = None
    currency: str | None = None
    cost_basis: str | None = None
    material_cost_estimated: bool = False
    used_material_cost_estimated: bool = False
    waste_cost_estimated: bool = False
    savings_percent_estimated: bool = False
    message: str


class OffcutPieceResponse(BaseModel):
    sheet_id: str
    instance: int
    area: float
    approx_shape: OffcutShape = "rectangle"
    bounds: BoundsPayload
    reusable: bool = True
    approximation: bool = True
    source: str


class OffcutSheetSummaryResponse(BaseModel):
    sheet_id: str
    instance: int
    sheet_area: float
    used_area: float
    scrap_area: float
    reusable_leftover_area: float
    estimated_scrap_area: float
    reusable_piece_count: int
    approximation: bool = True
    approximation_method: str
    message: str


class LeftoverSummaryResponse(BaseModel):
    sheet_id: str
    instance: int
    width: float
    height: float
    area: float
    approximate: bool = True
    source: str | None = None


class OffcutSummaryResponse(BaseModel):
    total_leftover_area: float
    reusable_leftover_area: float
    reusable_area_estimate: float | None = None
    estimated_scrap_area: float
    reusable_piece_count: int
    approximation: bool = True
    approximation_method: str
    message: str
    leftover_summaries: list[LeftoverSummaryResponse] = Field(default_factory=list)
    sheets: list[OffcutSheetSummaryResponse] = Field(default_factory=list)


class JobResponse(BaseModel):
    id: UUID
    state: JobState
    progress: float = 0.0
    status_message: str | None = None
    error: str | None = None
    error_type: str | None = None
    timed_out: bool = False
    timeout_seconds: float | None = None
    mode: Literal["fill_sheet", "batch_quantity"] | None = None
    summary: NestingPartsSummaryResponse | None = None
    parts: list[PartResultResponse] = Field(default_factory=list)
    batch: BatchInput | None = None
    artifact_url: str | None = None
    artifacts: list[ArtifactDescriptorResponse] = Field(default_factory=list)
    created_at: str | None = None
    queued_at: str | None = None
    started_at: str | None = None
    heartbeat_at: str | None = None
    finished_at: str | None = None
    run_number: int = 1
    compute_time_sec: float = 0.0
    current_yield: float = 0.0
    previous_yield: float = 0.0
    best_yield: float = 0.0
    improvement_percent: float = 0.0
    engine_backend_requested: Literal["python", "native"] | None = None
    engine_backend_used: Literal["python", "native"] | None = None
    engine_fallback_reason: str | None = None


class StructuredErrorResponse(BaseModel):
    status: Literal["ERROR"]
    error_code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    error_type: str | None = None
    backtrace: str | None = None
    input_digest: str | None = None
    exit_code: int | None = None
    artifact_dir: str | None = None


class NativePOCSafeResponse(BaseModel):
    status: Literal["OK", "ERROR"]
    result: dict[str, object] | None = None
    details: dict[str, object] = Field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None
    error_type: str | None = None
    backtrace: str | None = None
    input_digest: str | None = None
    exit_code: int | None = None
    artifact_dir: str | None = None


class PlacementResponse(BaseModel):
    part_id: str
    sheet_id: str
    instance: int
    rotation: int
    x: float
    y: float
    width: float
    height: float
    polygon: PolygonPayload
    order_id: str | None = None
    order_name: str | None = None
    priority: int | None = None


class SheetLayoutResponse(BaseModel):
    sheet_id: str
    instance: int
    width: float
    height: float
    placements: list[PlacementResponse]
    used_area: float
    scrap_area: float


class DebugBBox(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    width: float
    height: float


class DebugSheet(BaseModel):
    sheet_id: str
    instance: int
    width: float
    height: float
    area: float


class DebugPlacement(BaseModel):
    placement_id: str
    part_id: str
    sheet_id: str
    instance: int
    area: float
    bbox: DebugBBox
    valid: bool
    within_sheet: bool


class DebugScaleInfo(BaseModel):
    placement_bounds: DebugBBox | None = None
    max_extent: float
    sheet_max_extent: float
    extent_ratio: float
    cluster_flagged: bool


class NestingDebugResponse(BaseModel):
    sheet: DebugSheet | None = None
    sheets: list[DebugSheet]
    placements: list[DebugPlacement]
    total_used_area: float
    total_scrap_area: float
    scale_info: DebugScaleInfo
    warnings: list[str]


class NestingResultResponse(BaseModel):
    mode: Literal["fill_sheet", "batch_quantity"] = "batch_quantity"
    status: Literal["SUCCEEDED", "PARTIAL", "FAILED"] = "FAILED"
    summary: NestingPartsSummaryResponse
    yield_value: float = Field(alias="yield")
    yield_ratio: float | None = None
    scrap_ratio: float | None = None
    scrap_area: float
    used_area: float
    total_sheet_area: float
    parts_placed: int | None = None
    total_parts_placed: int | None = None
    layouts_used: int | None = None
    layouts: list[SheetLayoutResponse]
    parts: list[PartResultResponse] = Field(default_factory=list)
    batch: BatchInput | None = None
    artifacts: list[ArtifactDescriptorResponse] = Field(default_factory=list)
    economics: EconomicMetricsResponse | None = None
    offcuts: list[OffcutPieceResponse] = Field(default_factory=list)
    offcut_summary: OffcutSummaryResponse | None = None
    unplaced_parts: list[str]
    warnings: list[str] = Field(default_factory=list)
    debug: NestingDebugResponse | None = None
    job_id: UUID | None = None
    run_number: int = 1
    compute_time_sec: float = 0.0
    previous_yield: float = 0.0
    best_yield: float = 0.0
    improvement_percent: float = 0.0
    timed_out: bool = False
    optimization_history: list[dict] = Field(default_factory=list)
    engine_backend_requested: Literal["python", "native"] | None = None
    engine_backend_used: Literal["python", "native"] | None = None
    engine_fallback_reason: str | None = None

    model_config = {"populate_by_name": True}
