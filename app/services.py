from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from shapely.geometry import Polygon
from sqlalchemy.orm import Session

from app.artifacts import resolve_artifacts
from app.db import get_session_factory
from app.dxf_parser import parse_dxf_with_audit
from app.economics import build_economic_metrics
from app.geometry import clean_geometry as clean_geometry_impl, polygon_from_points, polygon_to_points
from app.models import JobState, NestingJob
from app.native_runner import NativeRunnerError, ensure_native_result_ready, run_native_poc
from app.nesting import PartSpec, SheetSpec, nest
from app.nesting_v2 import run_nesting as run_nesting_v2
from app.nesting_v3 import run_nesting as run_nesting_v3
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


class EngineRunTimeout(RuntimeError):
    def __init__(self, message: str, *, engine_backend: str, timeout_seconds: float) -> None:
        super().__init__(message)
        self.message = message
        self.engine_backend = engine_backend
        self.timeout_seconds = timeout_seconds

    @property
    def error_payload(self) -> dict[str, object]:
        return {
            "error_type": "timeout",
            "message": self.message,
            "engine_backend": self.engine_backend,
            "timed_out": True,
            "timeout_seconds": self.timeout_seconds,
        }

    def __str__(self) -> str:
        return json.dumps(self.error_payload, ensure_ascii=False)


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
    resolved_backend = payload.engine_backend or get_settings().engine_backend
    payload_data["engine_backend_requested"] = resolved_backend
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
                "order_id": str(part.get("order_id")) if part.get("order_id") is not None else None,
                "order_name": str(part.get("order_name")) if part.get("order_name") is not None else None,
                "priority": int(part.get("priority")) if isinstance(part.get("priority"), int) else None,
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


def _resolve_run_timeout_seconds(requested_time_limit_sec: float | None, settings) -> float:
    requested = float(requested_time_limit_sec or settings.max_compute_seconds)
    return max(1.0, min(requested, settings.max_compute_seconds, 60.0))


def _remaining_timeout_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.perf_counter())


def _encode_error_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _decode_error_payload(error_text: str | None) -> dict[str, object] | None:
    if not error_text:
        return None
    try:
        parsed = json.loads(error_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _error_payload_from_exception(exc: Exception, *, timeout_seconds: float | None = None) -> dict[str, object]:
    if isinstance(exc, EngineRunTimeout):
        return exc.error_payload
    if isinstance(exc, NativeRunnerError):
        payload = dict(exc.error_payload)
        payload["timed_out"] = payload.get("error_type") == "timeout"
        if payload["timed_out"] and timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return payload
    decoded = _decode_error_payload(str(exc))
    if decoded:
        decoded.setdefault("timed_out", decoded.get("error_type") == "timeout")
        if decoded.get("timed_out") and timeout_seconds is not None:
            decoded.setdefault("timeout_seconds", timeout_seconds)
        return decoded
    payload: dict[str, object] = {
        "error_type": "execution_error",
        "message": str(exc),
        "timed_out": False,
    }
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    return payload


def _fallback_reason_from_exception(exc: Exception) -> str:
    if isinstance(exc, NativeRunnerError):
        return exc.message
    decoded = _decode_error_payload(str(exc))
    if decoded and decoded.get("message"):
        return str(decoded["message"])
    return str(exc)


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


def _build_economic_metrics(result: dict | None, material: dict | None = None) -> dict[str, object]:
    return build_economic_metrics(material, result)


def serialize_job(job: NestingJob) -> dict:
    mode, summary, parts = _build_job_progress_parts(job)
    runtime = _job_runtime_metrics(job)
    payload = job.payload if isinstance(job.payload, dict) else {}
    result = _load_job_result_if_available(job) or {}
    artifacts = resolve_artifacts(job, result=result)
    artifact_url = next((artifact["url"] for artifact in artifacts if artifact["kind"] == "json"), None)
    error_payload = _decode_error_payload(job.error)
    return {
        "id": job.id,
        "state": job.state,
        "progress": float(job.progress or 0.0),
        "status_message": job.status_message,
        "error": job.error,
        "error_type": error_payload.get("error_type") if error_payload else None,
        "timed_out": bool(error_payload.get("timed_out")) if error_payload else False,
        "timeout_seconds": float(error_payload["timeout_seconds"]) if error_payload and error_payload.get("timeout_seconds") is not None else None,
        "mode": mode,
        "summary": summary,
        "parts": parts,
        "batch": result.get("batch") or payload.get("batch"),
        "artifact_url": artifact_url,
        "artifacts": artifacts,
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
        "engine_backend_requested": result.get("engine_backend_requested") or payload.get("engine_backend_requested"),
        "engine_backend_used": result.get("engine_backend_used") or payload.get("engine_backend_used"),
        "engine_fallback_reason": result.get("engine_fallback_reason") or payload.get("engine_fallback_reason"),
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


def _run_python_engine(
    *,
    job: NestingJob,
    payload: NestingJobCreateRequest,
    parts: list[PartSpec],
    sheets: list[SheetSpec],
    settings,
    previous_result: dict | None,
    progress_floor: float,
    timeout_seconds: float,
) -> dict:
    # Reserve shutdown/serialization headroom so the child can return a structured
    # partial result before the parent subprocess hard-times out.
    engine_compute_budget = max(0.1, timeout_seconds - min(10.0, max(timeout_seconds * 0.15, 2.0)))
    child_payload = {
        "parts": [
            {
                "part_id": part.part_id,
                "filename": part.filename,
                "quantity": part.quantity,
                "enabled": part.enabled,
                "fill_only": part.fill_only,
                "order_id": part.order_id,
                "order_name": part.order_name,
                "priority": part.priority,
                "polygon_points": polygon_to_points(part.polygon),
            }
            for part in parts
        ],
        "sheets": [
            {
                "sheet_id": sheet.sheet_id,
                "width": sheet.width,
                "height": sheet.height,
                "quantity": sheet.quantity,
            }
            for sheet in sheets
        ],
        "params": {
            **payload.params.model_dump(),
            "mode": payload.mode,
            "time_limit_sec": engine_compute_budget,
            "run_number": int((job.payload or {}).get("run_number", 1)),
            "previous_result": previous_result,
        },
    }
    update_job_status(
        job.id,
        state=JobState.RUNNING,
        progress=min(0.95, progress_floor),
        status_message="Python engine started with bounded timeout.",
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "from app.services import _python_engine_subprocess_main; _python_engine_subprocess_main()"],
            input=json.dumps(child_payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineRunTimeout(
            f"Python nesting engine timed out after {timeout_seconds:.1f}s",
            engine_backend="python",
            timeout_seconds=timeout_seconds,
        ) from exc

    if completed.returncode != 0:
        structured_error = _decode_error_payload(completed.stdout) or _decode_error_payload(completed.stderr)
        if structured_error:
            raise RuntimeError(_encode_error_payload(structured_error))
        raise RuntimeError(
            _encode_error_payload(
                {
                    "error_type": "python_engine_crash",
                    "message": completed.stderr.strip() or completed.stdout.strip() or f"Python nesting subprocess exited with code {completed.returncode}",
                    "timed_out": False,
                }
            )
        )

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            _encode_error_payload(
                {
                    "error_type": "python_engine_invalid_json",
                    "message": "Python nesting subprocess returned invalid JSON",
                    "timed_out": False,
                }
            )
        ) from exc


def _python_engine_subprocess_main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        parts = [
            PartSpec(
                part_id=str(part["part_id"]),
                filename=part.get("filename"),
                polygon=polygon_from_points(part["polygon_points"]),
                quantity=int(part["quantity"]),
                enabled=bool(part.get("enabled", True)),
                fill_only=bool(part.get("fill_only", False)),
                order_id=part.get("order_id"),
                order_name=part.get("order_name"),
                priority=int(part["priority"]) if part.get("priority") is not None else None,
            )
            for part in payload["parts"]
        ]
        sheets = [
            SheetSpec(
                sheet_id=str(sheet["sheet_id"]),
                width=float(sheet["width"]),
                height=float(sheet["height"]),
                quantity=int(sheet["quantity"]),
            )
            for sheet in payload["sheets"]
        ]
        result = nest(parts, sheets, payload["params"])
        serializable_result = {
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
                            "order_id": placement.order_id,
                            "order_name": placement.order_name,
                            "priority": placement.priority,
                            "polygon": {
                                "points": [{"x": x, "y": y} for x, y in polygon_to_points(placement.polygon)]
                            },
                        }
                        for placement in layout["placements"]
                    ],
                }
                for layout in result["layouts"]
            ],
        }
        print(json.dumps(serializable_result, ensure_ascii=False))
    except Exception as exc:
        print(
            _encode_error_payload(
                {
                    "error_type": "python_engine_error",
                    "message": str(exc),
                    "timed_out": False,
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def run_timeout_probe(seconds: float, timeout_seconds: float) -> float:
    command = [sys.executable, "-c", "import sys,time; time.sleep(float(sys.argv[1])); print(sys.argv[1])", str(seconds)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise EngineRunTimeout(
            f"Timeout probe exceeded {timeout_seconds:.1f}s",
            engine_backend="python",
            timeout_seconds=timeout_seconds,
        ) from exc
    return float(completed.stdout.strip())


def _adapt_v2_result(raw_result: dict, mode: str) -> dict:
    metrics = raw_result.get("metrics") if isinstance(raw_result.get("metrics"), dict) else {}
    sheet = raw_result.get("sheet") if isinstance(raw_result.get("sheet"), dict) else {}
    raw_placements = raw_result.get("placements") if isinstance(raw_result.get("placements"), list) else []
    parts = raw_result.get("parts") if isinstance(raw_result.get("parts"), list) else []

    total_sheet_area = float(metrics.get("sheet_area") or 0.0)
    used_area = float(metrics.get("used_area") or 0.0)
    scrap_area = float(metrics.get("waste_area") or max(total_sheet_area - used_area, 0.0))
    yield_value = float(metrics.get("yield_ratio") or metrics.get("yield") or 0.0)
    placed_parts = int(metrics.get("placed_parts") or metrics.get("placed_count") or len(raw_placements))
    status = str(raw_result.get("status") or "SUCCEEDED")

    # Normalize placements: extract width/height from bounds for PlacementResponse
    placements: list[dict] = []
    for pl in raw_placements:
        if not isinstance(pl, dict):
            continue
        bounds = pl.get("bounds") or {}
        w = float(pl.get("width") or bounds.get("width") or 0.0)
        h = float(pl.get("height") or bounds.get("height") or 0.0)
        placements.append({**pl, "width": w, "height": h})

    # Build unplaced_parts from per-part remaining_quantity
    unplaced_parts = [
        p["part_id"] for p in parts
        if isinstance(p, dict) and int(p.get("remaining_quantity") or 0) > 0
    ]
    # Status: PARTIAL when some requested parts couldn't be placed
    has_unplaced = bool(unplaced_parts) or int(metrics.get("unplaced_parts") or 0) > 0
    if status == "SUCCEEDED" and has_unplaced:
        status = "PARTIAL"
    warnings: list[str] = []
    if unplaced_parts:
        warnings.append(f"Parts with remaining quantity stays above zero: {', '.join(unplaced_parts)}")

    # Build layouts list (V2/V3 only use one sheet, group all placements into one layout)
    sheet_id = sheet.get("sheet_id", "sheet-1")
    sheet_w = float(sheet.get("width") or 0.0)
    sheet_h = float(sheet.get("height") or 0.0)
    if placements:
        layout_used_area = sum(float(pl.get("area") or 0.0) for pl in placements)
        layout_scrap = max(sheet_w * sheet_h - layout_used_area, 0.0)
        layouts: list[dict] = [{
            "sheet_id": sheet_id,
            "instance": 1,
            "width": sheet_w,
            "height": sheet_h,
            "used_area": layout_used_area,
            "scrap_area": layout_scrap,
            "placements": placements,
        }]
        layouts_used = 1
    else:
        layouts = []
        layouts_used = 0

    # Compute offcuts from placement polygons (approximated rectangular strips)
    offcuts: list[dict] = []
    offcut_summary: dict | None = None
    try:
        from app.offcuts import summarize_sheet_offcuts as _summarize_sheet
        from shapely.geometry import Polygon as _SPoly
        placement_polys = []
        for pl in placements:
            pts = (pl.get("polygon") or {}).get("points") or []
            if pts:
                try:
                    placement_polys.append(_SPoly([(p["x"], p["y"]) for p in pts]))
                except Exception:
                    pass
        if sheet_w > 0 and sheet_h > 0:
            _offcuts, _summary = _summarize_sheet(
                sheet_id=sheet_id,
                instance=1,
                sheet_width=sheet_w,
                sheet_height=sheet_h,
                used_area=layout_used_area if placements else 0.0,
                scrap_area=layout_scrap if placements else sheet_w * sheet_h,
                placement_polygons=placement_polys,
            )
            offcuts = _offcuts
            total_leftover = float(_summary.get("scrap_area") or 0.0)
            reusable = float(_summary.get("reusable_leftover_area") or 0.0)
            offcut_summary = {
                **_summary,
                "total_leftover_area": total_leftover,
                "reusable_area_estimate": reusable,
                "leftover_summaries": [
                    {
                        "sheet_id": o.get("sheet_id", sheet_id),
                        "instance": o.get("instance", 1),
                        "width": float((o.get("bounds") or {}).get("width") or 0.0),
                        "height": float((o.get("bounds") or {}).get("height") or 0.0),
                        "area": float(o.get("area") or 0.0),
                        "approximate": o.get("approximation") is not False,
                        "source": str(o.get("source") or "unknown"),
                    }
                    for o in offcuts
                ],
            }
    except Exception:
        pass

    return {
        "status": status,
        "mode": mode,
        "yield": yield_value,
        "yield_ratio": yield_value,
        "scrap_ratio": round(1.0 - yield_value, 6) if total_sheet_area > 0 else 0.0,
        "scrap_area": scrap_area,
        "used_area": used_area,
        "total_sheet_area": total_sheet_area,
        "parts_placed": placed_parts,
        "total_parts_placed": placed_parts,
        "layouts_used": layouts_used,
        "layouts": layouts,
        "placements": placements,
        "parts": parts,
        "sheet": sheet,
        "unplaced_parts": unplaced_parts,
        "warnings": warnings,
        "offcuts": offcuts,
        "offcut_summary": offcut_summary,
        "timed_out": bool(raw_result.get("timed_out")),
        "summary": {
            "total_parts": int(metrics.get("total_parts") or len(parts)),
            "placed_parts": placed_parts,
            "yield_ratio": yield_value,
            "used_area": used_area,
            "scrap_area": scrap_area,
            "total_sheet_area": total_sheet_area,
            "mode": mode,
            "engine": raw_result.get("engine", "v2"),
        },
    }


def _run_v2_engine(
    *,
    payload: NestingJobCreateRequest,
    parts: list[PartSpec],
    sheets: list[SheetSpec],
    timeout_seconds: float,
) -> dict:
    if not sheets:
        raise ValueError("At least one sheet is required for the v2 nesting engine")

    raw_result = run_nesting_v2(
        parts=parts,
        sheet=sheets[0],
        settings={
            **payload.params.model_dump(),
            "mode": payload.mode,
            "time_limit_sec": timeout_seconds,
        },
    )
    return _adapt_v2_result(raw_result, payload.mode)


def _run_v3_engine(
    *,
    payload: NestingJobCreateRequest,
    parts: list[PartSpec],
    sheets: list[SheetSpec],
    timeout_seconds: float,
) -> dict:
    """v3 engine: multi-start randomised greedy + rotation local search."""
    if not sheets:
        raise ValueError("At least one sheet is required for the v3 nesting engine")

    raw_result = run_nesting_v3(
        parts=parts,
        sheet=sheets[0],
        settings={
            **payload.params.model_dump(),
            "mode": payload.mode,
            "time_limit_sec": timeout_seconds,
        },
    )
    adapted = _adapt_v2_result(raw_result, payload.mode)
    v3_info = raw_result.get("v3_info")
    if isinstance(v3_info, dict):
        adapted.setdefault("summary", {})["v3_info"] = v3_info
    return adapted


def _run_nesting_backend(
    *,
    job: NestingJob,
    payload: NestingJobCreateRequest,
    parts: list[PartSpec],
    sheets: list[SheetSpec],
    settings,
    previous_result: dict | None,
    deadline: float,
    job_timeout_seconds: float,
) -> tuple[dict, str, str | None]:
    requested_backend = str((job.payload or {}).get("engine_backend_requested") or payload.engine_backend or settings.engine_backend)
    if requested_backend == "python":
        requested_backend = "v3"
    # fill_sheet mode is only supported by V1; fall back for V2/V3
    if payload.mode == "fill_sheet" and requested_backend in ("v2", "v3"):
        requested_backend = "python"
    fallback_reason: str | None = None
    remaining_for_python: float | None = None

    if requested_backend == "v3":
        remaining = _remaining_timeout_seconds(deadline)
        if remaining <= 0:
            raise EngineRunTimeout(
                f"v3 backend timed out after {job_timeout_seconds:.1f}s before execution began",
                engine_backend="v3",
                timeout_seconds=job_timeout_seconds,
            )
        update_job_status(
            job.id,
            state=JobState.RUNNING,
            progress=0.50,
            status_message="v3 engine started (multi-start greedy + rotation local search).",
        )
        return _run_v3_engine(payload=payload, parts=parts, sheets=sheets, timeout_seconds=remaining), "v3", None
    elif requested_backend == "v2":
        remaining = _remaining_timeout_seconds(deadline)
        if remaining <= 0:
            raise EngineRunTimeout(
                f"v2 backend timed out after {job_timeout_seconds:.1f}s before execution began",
                engine_backend="v2",
                timeout_seconds=job_timeout_seconds,
            )
        update_job_status(
            job.id,
            state=JobState.RUNNING,
            progress=0.50,
            status_message="v2 engine started.",
        )
        return _run_v2_engine(payload=payload, parts=parts, sheets=sheets, timeout_seconds=remaining), "v2", None
    elif requested_backend == "native":
        if not settings.native_poc_enabled:
            fallback_reason = "Native backend requested, but NESTING_NATIVE_POC_ENABLED is false."
            logger.warning("Native backend disabled for job %s; falling back to python engine", job.id)
            remaining_for_python = _remaining_timeout_seconds(deadline)
            if remaining_for_python <= 0:
                raise EngineRunTimeout(
                    f"Job exhausted its {job_timeout_seconds:.1f}s budget before Python fallback could start",
                    engine_backend="native",
                    timeout_seconds=job_timeout_seconds,
                )
            update_job_status(
                job.id,
                state=JobState.RUNNING,
                progress=0.5,
                status_message="Native backend disabled; falling back to Python engine.",
            )
        else:
            remaining_for_native = _remaining_timeout_seconds(deadline)
            if remaining_for_native <= 0:
                raise EngineRunTimeout(
                    f"Native backend timed out after {job_timeout_seconds:.1f}s before execution began",
                    engine_backend="native",
                    timeout_seconds=job_timeout_seconds,
                )
            update_job_status(job.id, state=JobState.RUNNING, progress=0.45, status_message="Attempting native nesting backend.")
            try:
                native_result = ensure_native_result_ready(
                    run_native_poc(
                        parts,
                        sheets,
                        {
                            **payload.params.model_dump(),
                            "mode": payload.mode,
                            "time_limit_sec": remaining_for_native,
                        },
                    )
                )
                logger.info(
                    "Native backend produced a stable result for job %s input_digest=%s",
                    job.id,
                    native_result.input_digest,
                )
                result_payload = native_result.payload if isinstance(native_result.payload, dict) else {}
                return result_payload, "native", None
            except Exception as exc:
                fallback_reason = _fallback_reason_from_exception(exc)
                logger.warning("Native backend failed for job %s; falling back to python engine: %s", job.id, fallback_reason)
                remaining_for_python = _remaining_timeout_seconds(deadline)
                if remaining_for_python <= 0:
                    raise EngineRunTimeout(
                        f"Job exhausted its {job_timeout_seconds:.1f}s budget before Python fallback could start",
                        engine_backend="native",
                        timeout_seconds=job_timeout_seconds,
                    )
                update_job_status(
                    job.id,
                    state=JobState.RUNNING,
                    progress=0.5,
                    status_message="Native backend failed; falling back to Python engine.",
                )
    else:
        remaining_for_python = _remaining_timeout_seconds(deadline)
        if remaining_for_python <= 0:
            raise EngineRunTimeout(
                f"Python backend timed out after {job_timeout_seconds:.1f}s before execution began",
                engine_backend="python",
                timeout_seconds=job_timeout_seconds,
            )
        remaining_for_python = remaining_for_python or _remaining_timeout_seconds(deadline)

    result = _run_python_engine(
        job=job,
        payload=payload,
        parts=parts,
        sheets=sheets,
        settings=settings,
        previous_result=previous_result,
        progress_floor=0.55,
        timeout_seconds=remaining_for_python,
    )
    return result, "python", fallback_reason


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
    requested_backend = str((job.payload or {}).get("engine_backend_requested") or payload.engine_backend or settings.engine_backend)
    if isinstance(job.payload, dict):
        job.payload["engine_backend_requested"] = requested_backend
        job.payload.pop("engine_backend_used", None)
        job.payload.pop("engine_fallback_reason", None)
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

    job_timeout_seconds = _resolve_run_timeout_seconds(payload.params.model_dump().get("time_limit_sec"), settings)
    if isinstance(job.payload, dict):
        job.payload["timeout_seconds"] = job_timeout_seconds
    deadline = time.perf_counter() + job_timeout_seconds

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
                order_id=part.order_id,
                order_name=part.order_name,
                priority=part.priority,
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

        update_job_status(job.id, state=JobState.RUNNING, progress=0.4, status_message="Preparing nesting engine.")
        started = time.perf_counter()
        result, engine_backend_used, fallback_reason = _run_nesting_backend(
            job=job,
            payload=payload,
            parts=parts,
            sheets=sheets,
            settings=settings,
            previous_result=previous_result,
            deadline=deadline,
            job_timeout_seconds=job_timeout_seconds,
        )
        duration_seconds = round(min(time.perf_counter() - started, job_timeout_seconds), 3)
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
            "engine_backend_requested": requested_backend,
            "engine_backend_used": engine_backend_used,
            "engine_fallback_reason": fallback_reason,
            "timeout_seconds": job_timeout_seconds,
            "batch": payload.batch.model_dump(mode="json") if payload.batch else result.get("batch"),
            "artifacts": resolve_artifacts(job),
            "economics": _build_economic_metrics(result, payload.material.model_dump(mode="json") if payload.material else None),
        }
        result_path = save_job_result(job.id, serializable)
        artifact_path = str(result_path)
        final_status = str(result.get("status") or "FAILED")
        job.state = JobState.PARTIAL if final_status == "PARTIAL" else JobState.SUCCEEDED
        job.result_path = str(result_path)
        job.artifact_path = artifact_path
        serializable["artifacts"] = resolve_artifacts(job, result=serializable)
        job.progress = 1.0
        job.status_message = (
            f"Job finished successfully in {duration_seconds:.3f}s."
            if job.state == JobState.SUCCEEDED
            else f"Job returned the best-so-far partial result in {duration_seconds:.3f}s."
        )
        if isinstance(job.payload, dict):
            job.payload["engine_backend_used"] = engine_backend_used
            job.payload["engine_fallback_reason"] = fallback_reason
        job.finished_at = utcnow()
        job.heartbeat_at = job.finished_at
        db.add(job)
        db.commit()
        save_job_result(job.id, serializable)
        logger.info("Job %s finished with state=%s in %.3fs", job.id, job.state, duration_seconds)
        return serializable
    except Exception as exc:
        error_payload = _error_payload_from_exception(exc, timeout_seconds=job_timeout_seconds)
        job.state = JobState.FAILED
        job.error = _encode_error_payload(error_payload)
        job.progress = min(float(job.progress or 0.0), 0.95)
        if error_payload.get("timed_out"):
            job.status_message = f"Job timed out after {float(error_payload.get('timeout_seconds') or job_timeout_seconds):.1f}s."
        else:
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
    result = load_job_result(path)
    if not isinstance(result, dict):
        return result
    result["artifacts"] = resolve_artifacts(job, result=result)
    payload = job.payload if isinstance(job.payload, dict) else {}
    material = payload.get("material") if isinstance(payload.get("material"), dict) else None
    result.setdefault("economics", _build_economic_metrics(result, material))
    return result
