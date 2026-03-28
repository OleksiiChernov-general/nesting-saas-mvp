from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import JobState


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


class SheetInput(BaseModel):
    sheet_id: str = "sheet-1"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1)
    units: str = "mm"


class NestingParams(BaseModel):
    gap: float = Field(default=0.0, ge=0)
    rotation: list[Literal[0, 90, 180, 270]] = Field(default_factory=lambda: [0, 180])
    objective: str = "maximize_yield"
    debug: bool = False
    source_units: str | None = None
    source_max_extent: float | None = Field(default=None, gt=0)


class NestingJobCreateRequest(BaseModel):
    mode: Literal["fill_sheet", "batch_quantity"]
    parts: list[PartInput]
    sheet: SheetInput | None = None
    sheets: list[SheetInput] = Field(default_factory=list)
    params: NestingParams = Field(default_factory=NestingParams)

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


class JobResponse(BaseModel):
    id: UUID
    state: JobState
    progress: float = 0.0
    status_message: str | None = None
    error: str | None = None
    mode: Literal["fill_sheet", "batch_quantity"] | None = None
    summary: NestingPartsSummaryResponse | None = None
    parts: list[PartResultResponse] = Field(default_factory=list)
    artifact_url: str | None = None
    created_at: str | None = None
    queued_at: str | None = None
    started_at: str | None = None
    heartbeat_at: str | None = None
    finished_at: str | None = None


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
    unplaced_parts: list[str]
    warnings: list[str] = Field(default_factory=list)
    debug: NestingDebugResponse | None = None

    model_config = {"populate_by_name": True}
