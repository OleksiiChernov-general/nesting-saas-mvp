from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

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


class ImportResponse(BaseModel):
    import_id: str
    filename: str
    polygons: list[PolygonPayload]
    invalid_shapes: list[InvalidShape]


class CleanGeometryRequest(BaseModel):
    polygons: list[PolygonPayload]
    tolerance: float = Field(default=0.5, gt=0)


class CleanGeometryResponse(BaseModel):
    polygons: list[PolygonPayload]
    removed: int
    invalid_shapes: list[InvalidShape]


class PartInput(BaseModel):
    part_id: str
    polygon: PolygonPayload
    quantity: int = Field(default=1, ge=1)


class SheetInput(BaseModel):
    sheet_id: str
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1)


class NestingParams(BaseModel):
    gap: float = Field(default=0.0, ge=0)
    rotation: list[Literal[0, 180]] = Field(default_factory=lambda: [0, 180])
    objective: str = "maximize_yield"
    debug: bool = False


class NestingJobCreateRequest(BaseModel):
    parts: list[PartInput]
    sheets: list[SheetInput]
    params: NestingParams = Field(default_factory=NestingParams)


class JobResponse(BaseModel):
    id: UUID
    state: JobState
    progress: float = 0.0
    status_message: str | None = None
    error: str | None = None
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
    yield_value: float = Field(alias="yield")
    yield_ratio: float | None = None
    scrap_ratio: float | None = None
    scrap_area: float
    used_area: float
    total_sheet_area: float
    parts_placed: int | None = None
    layouts_used: int | None = None
    layouts: list[SheetLayoutResponse]
    unplaced_parts: list[str]
    debug: NestingDebugResponse | None = None

    model_config = {"populate_by_name": True}
