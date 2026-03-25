from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from shapely.geometry import Polygon
from sqlalchemy.orm import Session

from app.db import get_session_factory
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
from app.settings import get_settings


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


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
    job = NestingJob(
        payload=payload.model_dump(mode="json"),
        state=JobState.CREATED,
        progress=0.0,
        status_message="Job created.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_queued(db: Session, job: NestingJob) -> NestingJob:
    job.state = JobState.QUEUED
    job.progress = 0.05
    job.status_message = "Job queued for worker execution."
    job.queue_attempts = (job.queue_attempts or 0) + 1
    job.queued_at = utcnow()
    job.heartbeat_at = job.queued_at
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def serialize_job(job: NestingJob) -> dict:
    artifact_url = f"/v1/nesting/jobs/{job.id}/artifact" if job.artifact_path else None
    return {
        "id": job.id,
        "state": job.state,
        "progress": float(job.progress or 0.0),
        "status_message": job.status_message,
        "error": job.error,
        "artifact_url": artifact_url,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def update_job_status(
    job_id: UUID,
    *,
    state: JobState | None = None,
    progress: float | None = None,
    status_message: str | None = None,
    error: str | None = None,
    finished: bool = False,
    artifact_path: str | None = None,
    result_path: str | None = None,
) -> None:
    with get_session_factory()() as db:
        job = db.get(NestingJob, job_id)
        if not job:
            return
        if state is not None:
            job.state = state
        if progress is not None:
            job.progress = progress
        if status_message is not None:
            job.status_message = status_message
        if error is not None:
            job.error = error
        if result_path is not None:
            job.result_path = result_path
        if artifact_path is not None:
            job.artifact_path = artifact_path
        job.heartbeat_at = utcnow()
        if finished:
            job.finished_at = utcnow()
        db.add(job)
        db.commit()


def recover_stale_jobs() -> None:
    timeout_seconds = get_settings().stale_job_timeout_seconds
    cutoff = utcnow().timestamp() - timeout_seconds
    with get_session_factory()() as db:
        jobs = (
            db.query(NestingJob)
            .filter(NestingJob.state.in_([JobState.QUEUED, JobState.RUNNING]))
            .all()
        )
        recovered = 0
        for job in jobs:
            reference_time = job.heartbeat_at or job.started_at or job.queued_at or job.created_at
            if reference_time is None or reference_time.timestamp() >= cutoff:
                continue
            job.state = JobState.FAILED
            job.progress = min(float(job.progress or 0.0), 0.95)
            job.status_message = "Job marked failed after stale worker timeout."
            job.error = "Worker stopped heartbeating before the job finished."
            job.finished_at = utcnow()
            db.add(job)
            recovered += 1
        if recovered:
            db.commit()
            logger.warning("Recovered %s stale job(s)", recovered)


def run_nesting_job(db: Session, job: NestingJob) -> dict:
    payload = NestingJobCreateRequest.model_validate(job.payload)
    job.state = JobState.RUNNING
    job.error = None
    job.progress = 0.15
    job.status_message = "Worker accepted job."
    job.started_at = utcnow()
    job.heartbeat_at = job.started_at
    db.add(job)
    db.commit()

    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        while not stop_heartbeat.wait(get_settings().job_heartbeat_interval_seconds):
            update_job_status(
                job.id,
                state=JobState.RUNNING,
                progress=max(float(job.progress or 0.0), 0.25),
                status_message="Nesting job is still running.",
            )

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()

    try:
        update_job_status(job.id, state=JobState.RUNNING, progress=0.3, status_message="Validating nesting input.")
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
        update_job_status(job.id, state=JobState.RUNNING, progress=0.55, status_message="Computing nesting layout.")
        started = time.perf_counter()
        result = nest(parts, sheets, payload.params.model_dump())
        duration_seconds = round(time.perf_counter() - started, 3)
        serializable = {
            **result,
            "job_id": str(job.id),
            "duration_seconds": duration_seconds,
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
        artifact_path = str(result_path)
        job.state = JobState.SUCCEEDED
        job.result_path = str(result_path)
        job.artifact_path = artifact_path
        job.progress = 1.0
        job.status_message = f"Job finished successfully in {duration_seconds:.3f}s."
        job.finished_at = utcnow()
        job.heartbeat_at = job.finished_at
        db.add(job)
        db.commit()
        logger.info("Job %s finished in %.3fs", job.id, duration_seconds)
        return serializable
    except Exception as exc:
        job.state = JobState.FAILED
        job.error = str(exc)
        job.progress = min(float(job.progress or 0.0), 0.95)
        job.status_message = "Job failed during nesting execution."
        job.finished_at = utcnow()
        job.heartbeat_at = job.finished_at
        db.add(job)
        db.commit()
        logger.exception("Job %s failed", job.id)
        raise
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=0.2)


def get_job_result(job: NestingJob) -> dict:
    if not job.result_path:
        raise FileNotFoundError("Result is not available")
    path = Path(job.result_path)
    if not path.exists():
        raise FileNotFoundError(f"Result file does not exist: {path}")
    return load_job_result(path)
