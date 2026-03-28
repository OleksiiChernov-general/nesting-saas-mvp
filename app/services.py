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
from app.dxf_parser import parse_dxf_with_audit
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
    started = time.perf_counter()
    parsed = parse_dxf_with_audit(file_path, tolerance=tolerance)
    elapsed = time.perf_counter() - started
    logger.info(
        "Imported DXF %s in %.3fs (polygons=%s invalid=%s units=%s)",
        filename,
        elapsed,
        len(parsed.polygons),
        len(parsed.invalid_shapes),
        parsed.audit.detected_units or "unknown",
    )
    return ImportResponse(
        import_id=import_id,
        filename=filename,
        polygons=[{"points": [{"x": x, "y": y} for x, y in polygon_to_points(poly)]} for poly in parsed.polygons],
        invalid_shapes=[InvalidShape(source=item.source, reason=item.reason) for item in parsed.invalid_shapes],
        audit=parsed.audit.__dict__,
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
    payload_data = payload.model_dump(mode="json")
    previous_yield = 0.0
    best_yield = 0.0
    run_number = 1

    if payload.previous_job_id:
        previous_job = db.get(NestingJob, payload.previous_job_id)
        previous_result = _load_job_result_if_available(previous_job) if previous_job else None
        if previous_result:
            previous_yield = float(previous_result.get("yield_ratio") or previous_result.get("yield") or 0.0)
            best_yield = float(previous_result.get("best_yield") or previous_yield)
            run_number = int(previous_result.get("run_number") or 1) + 1

    payload_data["run_number"] = run_number
    payload_data["previous_yield"] = previous_yield
    payload_data["best_yield"] = best_yield
    job = NestingJob(
        payload=payload_data,
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


def _build_job_progress_parts(job: NestingJob) -> tuple[str | None, dict | None, list[dict]]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    mode = payload.get("mode") if payload.get("mode") in {"fill_sheet", "batch_quantity"} else None
    payload_parts = payload.get("parts") if isinstance(payload.get("parts"), list) else []
    enabled_parts = [part for part in payload_parts if isinstance(part, dict) and part.get("enabled", True) is not False]

    if job.result_path:
        try:
            result = load_job_result(Path(job.result_path))
            if isinstance(result, dict):
                result_mode = result.get("mode")
                result_summary = result.get("summary")
                result_parts = result.get("parts")
                if result_mode in {"fill_sheet", "batch_quantity"} and isinstance(result_summary, dict) and isinstance(result_parts, list):
                    return result_mode, result_summary, result_parts
        except FileNotFoundError:
            pass

    progress_parts: list[dict] = []
    for index, part in enumerate(enabled_parts):
        quantity = part.get("quantity")
        requested_quantity = quantity if isinstance(quantity, int) and quantity >= 1 else 1
        progress_parts.append(
            {
                "part_id": str(part.get("part_id") or f"part-{index + 1}"),
                "filename": str(part.get("filename")) if part.get("filename") is not None else None,
                "requested_quantity": requested_quantity,
                "placed_quantity": 0,
                "remaining_quantity": requested_quantity,
                "enabled": True,
                "area_contribution": 0.0,
            }
        )

    return mode, {"total_parts": len(enabled_parts)}, progress_parts


def _load_job_result_if_available(job: NestingJob) -> dict | None:
    if not job.result_path:
        return None
    try:
        result = load_job_result(Path(job.result_path))
    except FileNotFoundError:
        return None
    return result if isinstance(result, dict) else None


def _calculate_improvement_percent(current_yield: float, previous_yield: float) -> float:
    if previous_yield <= 0:
        return 0.0
    return ((current_yield - previous_yield) / previous_yield) * 100.0


def _job_runtime_metrics(job: NestingJob) -> dict[str, float | int]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    result = _load_job_result_if_available(job)
    if result:
        return {
            "run_number": int(result.get("run_number") or payload.get("run_number") or 1),
            "compute_time_sec": float(result.get("compute_time_sec") or result.get("duration_seconds") or 0.0),
            "current_yield": float(result.get("yield_ratio") or result.get("yield") or 0.0),
            "previous_yield": float(result.get("previous_yield") or 0.0),
            "best_yield": float(result.get("best_yield") or result.get("yield_ratio") or result.get("yield") or 0.0),
            "improvement_percent": float(result.get("improvement_percent") or 0.0),
        }

    return {
        "run_number": int(payload.get("run_number") or 1),
        "compute_time_sec": 0.0,
        "current_yield": 0.0,
        "previous_yield": float(payload.get("previous_yield") or 0.0),
        "best_yield": float(payload.get("best_yield") or 0.0),
        "improvement_percent": 0.0,
    }


def serialize_job(job: NestingJob) -> dict:
    artifact_url = f"/v1/nesting/jobs/{job.id}/artifact" if job.artifact_path else None
    mode, summary, parts = _build_job_progress_parts(job)
    runtime = _job_runtime_metrics(job)
    return {
        "id": job.id,
        "state": job.state,
        "progress": float(job.progress or 0.0),
        "status_message": job.status_message,
        "error": job.error,
        "mode": mode,
        "summary": summary,
        "parts": parts,
        "artifact_url": artifact_url,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "run_number": runtime["run_number"],
        "compute_time_sec": runtime["compute_time_sec"],
        "current_yield": runtime["current_yield"],
        "previous_yield": runtime["previous_yield"],
        "best_yield": runtime["best_yield"],
        "improvement_percent": runtime["improvement_percent"],
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
    settings = get_settings()
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
                quantity=part.quantity or 1,
                filename=part.filename,
                enabled=part.enabled,
                fill_only=part.fill_only,
            )
            for part in payload.parts
        ]
        sheets = [
            SheetSpec(sheet_id=sheet.sheet_id, width=sheet.width, height=sheet.height, quantity=sheet.quantity)
            for sheet in payload.sheets
        ]
        previous_result: dict | None = None
        if payload.previous_job_id:
            previous_job = db.get(NestingJob, payload.previous_job_id)
            previous_result = _load_job_result_if_available(previous_job) if previous_job else None

        update_job_status(job.id, state=JobState.RUNNING, progress=0.55, status_message="Computing nesting layout within 60-second limit.")
        started = time.perf_counter()
        progress_floor = 0.55

        def report_engine_progress(fraction: float, message: str) -> None:
            clamped = min(max(fraction, 0.0), 1.0)
            update_job_status(
                job.id,
                state=JobState.RUNNING,
                progress=min(0.95, progress_floor + (clamped * 0.4)),
                status_message=message,
            )

        result = nest(
            parts,
            sheets,
            {
                **payload.params.model_dump(),
                "mode": payload.mode,
                "time_limit_sec": settings.max_compute_seconds,
                "run_number": int((job.payload or {}).get("run_number", 1)),
                "previous_result": previous_result,
                "progress_callback": report_engine_progress,
            },
        )
        duration_seconds = round(min(time.perf_counter() - started, settings.max_compute_seconds), 3)
        current_yield = float(result.get("yield_ratio") or result.get("yield") or 0.0)
        previous_yield = float((job.payload or {}).get("previous_yield") or 0.0)
        best_yield = max(float((job.payload or {}).get("best_yield") or 0.0), current_yield)
        improvement_percent = _calculate_improvement_percent(current_yield, previous_yield)
        optimization_history = list(previous_result.get("optimization_history", [])) if previous_result else []
        optimization_history.append(
            {
                "job_id": str(job.id),
                "run_number": int((job.payload or {}).get("run_number", 1)),
                "status": result.get("status", "FAILED"),
                "yield": current_yield,
                "compute_time_sec": duration_seconds,
                "improvement_percent": improvement_percent,
            }
        )
        serializable = {
            **result,
            "job_id": str(job.id),
            "duration_seconds": duration_seconds,
            "compute_time_sec": duration_seconds,
            "run_number": int((job.payload or {}).get("run_number", 1)),
            "previous_yield": previous_yield,
            "best_yield": best_yield,
            "improvement_percent": improvement_percent,
            "optimization_history": optimization_history,
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
        final_status = str(result.get("status") or "FAILED")
        job.state = JobState.PARTIAL if final_status == "PARTIAL" else JobState.SUCCEEDED
        job.result_path = str(result_path)
        job.artifact_path = artifact_path
        job.progress = 1.0
        job.status_message = (
            f"Job finished successfully in {duration_seconds:.3f}s."
            if job.state == JobState.SUCCEEDED
            else f"Job returned the best-so-far partial result in {duration_seconds:.3f}s."
        )
        job.finished_at = utcnow()
        job.heartbeat_at = job.finished_at
        db.add(job)
        db.commit()
        logger.info("Job %s finished with state=%s in %.3fs", job.id, job.state, duration_seconds)
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
