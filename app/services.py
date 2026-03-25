from __future__ import annotations

from pathlib import Path

from shapely.geometry import Polygon
from sqlalchemy.orm import Session

from app.dxf_parser import parse_dxf
from app.geometry import clean_geometry as clean_geometry_impl, polygon_from_points, polygon_to_points
from app.models import JobState, NestingJob
from app.nesting import PartSpec, SheetSpec, nest
from app.schemas import (
    CleanGeometryRequest,
    CleanGeometryResponse,
    ImportResponse,
    InvalidShape,
    NestingJobCreateRequest,
)
from app.storage import load_job_result, save_job_result


def import_dxf(file_path: str, filename: str, import_id: str, tolerance: float) -> ImportResponse:
    polygons, invalid_shapes = parse_dxf(file_path, tolerance=tolerance)
    return ImportResponse(
        import_id=import_id,
        filename=filename,
        polygons=[{"points": [{"x": x, "y": y} for x, y in polygon_to_points(poly)]} for poly in polygons],
        invalid_shapes=[InvalidShape(source=item.source, reason=item.reason) for item in invalid_shapes],
    )


def clean_geometry_payload(payload: CleanGeometryRequest) -> CleanGeometryResponse:
    polygons: list[Polygon] = [
        polygon_from_points([(point.x, point.y) for point in polygon.points]) for polygon in payload.polygons
    ]
    cleaned, issues = clean_geometry_impl(polygons, tolerance=payload.tolerance)
    return CleanGeometryResponse(
        polygons=[{"points": [{"x": x, "y": y} for x, y in polygon_to_points(poly)]} for poly in cleaned],
        removed=max(len(polygons) - len(cleaned), 0),
        invalid_shapes=[InvalidShape(source=issue.source, reason=issue.reason) for issue in issues],
    )


def create_job_record(db: Session, payload: NestingJobCreateRequest) -> NestingJob:
    job = NestingJob(payload=payload.model_dump(mode="json"), state=JobState.CREATED)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_nesting_job(db: Session, job: NestingJob) -> dict:
    payload = NestingJobCreateRequest.model_validate(job.payload)
    job.state = JobState.RUNNING
    job.error = None
    db.add(job)
    db.commit()

    try:
        parts = [
            PartSpec(
                part_id=part.part_id,
                polygon=polygon_from_points([(point.x, point.y) for point in part.polygon.points]),
                quantity=part.quantity,
            )
            for part in payload.parts
        ]
        sheets = [
            SheetSpec(sheet_id=sheet.sheet_id, width=sheet.width, height=sheet.height, quantity=sheet.quantity)
            for sheet in payload.sheets
        ]
        result = nest(parts, sheets, payload.params.model_dump())
        serializable = {
            **result,
            "layouts": [
                {
                    **layout,
                    "placements": [
                        {
                            "part_id": placement.part_id,
                            "sheet_id": placement.sheet_id,
                            "instance": placement.instance,
                            "rotation": placement.rotation,
                            "x": placement.x,
                            "y": placement.y,
                            "width": placement.polygon.bounds[2] - placement.polygon.bounds[0],
                            "height": placement.polygon.bounds[3] - placement.polygon.bounds[1],
                            "polygon": {
                                "points": [
                                    {"x": x, "y": y} for x, y in polygon_to_points(placement.polygon)
                                ]
                            },
                        }
                        for placement in layout["placements"]
                    ],
                }
                for layout in result["layouts"]
            ],
        }
        result_path = save_job_result(job.id, serializable)
        job.state = JobState.SUCCEEDED
        job.result_path = str(result_path)
        db.add(job)
        db.commit()
        return serializable
    except Exception as exc:
        job.state = JobState.FAILED
        job.error = str(exc)
        db.add(job)
        db.commit()
        raise


def get_job_result(job: NestingJob) -> dict:
    if not job.result_path:
        raise FileNotFoundError("Result is not available")
    path = Path(job.result_path)
    if not path.exists():
        raise FileNotFoundError(f"Result file does not exist: {path}")
    return load_job_result(path)
