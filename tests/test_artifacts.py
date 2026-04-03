from __future__ import annotations

import json
from uuid import uuid4

from app.artifacts import ensure_artifact, resolve_artifact
from app.models import JobState, NestingJob
from app.storage import artifact_error_path, artifact_store_path, save_job_result


def _job(
    *,
    state: JobState,
    payload: dict | None = None,
    result_path: str | None = None,
    artifact_path: str | None = None,
) -> NestingJob:
    return NestingJob(
        id=uuid4(),
        state=state,
        payload=payload or {},
        result_path=result_path,
        artifact_path=artifact_path,
        progress=1.0 if state in {JobState.SUCCEEDED, JobState.PARTIAL} else 0.0,
    )


def test_resolve_artifact_marks_dxf_unavailable_without_layouts(app_env) -> None:
    job = _job(state=JobState.SUCCEEDED)
    result_path = save_job_result(
        job.id,
        {
            "status": "SUCCEEDED",
            "summary": {"total_parts": 0},
            "layouts": [],
            "parts": [],
            "unplaced_parts": [],
        },
    )
    job.result_path = str(result_path)
    job.artifact_path = str(result_path)

    descriptor = resolve_artifact(job, "dxf")

    assert descriptor["status"] == "unavailable"
    assert "no layout geometry" in descriptor["message"].lower()
    assert descriptor["url"] is None


def test_resolve_artifact_marks_failed_when_error_marker_exists(app_env) -> None:
    job = _job(state=JobState.SUCCEEDED)
    result_path = save_job_result(
        job.id,
        {
            "status": "SUCCEEDED",
            "summary": {"total_parts": 1},
            "layouts": [{"sheet_id": "sheet-1", "instance": 1, "width": 100, "height": 100, "placements": []}],
            "parts": [],
            "unplaced_parts": [],
        },
    )
    job.result_path = str(result_path)
    job.artifact_path = str(result_path)
    error_path = artifact_error_path(job.id, "pdf")
    error_path.write_text("PDF export failed: renderer unavailable", encoding="utf-8")

    descriptor = resolve_artifact(job, "pdf")

    assert descriptor["status"] == "failed"
    assert descriptor["message"] == "PDF export failed: renderer unavailable"
    assert descriptor["url"] is None


def test_ensure_artifact_writes_pdf_and_clears_stale_error_marker(app_env) -> None:
    job = _job(
        state=JobState.SUCCEEDED,
        payload={
            "material": {
                "name": "Steel",
                "thickness": 3,
                "sheet_width": 100,
                "sheet_height": 100,
                "units": "mm",
            }
        },
    )
    result_path = save_job_result(
        job.id,
        {
            "status": "SUCCEEDED",
            "summary": {"total_parts": 1},
            "yield_ratio": 0.8,
            "scrap_ratio": 0.2,
            "total_parts_placed": 1,
            "material": {"name": "Steel", "thickness": 3, "sheet_width": 100, "sheet_height": 100, "units": "mm"},
            "layouts": [{"sheet_id": "sheet-1", "instance": 1, "width": 100, "height": 100, "placements": []}],
            "parts": [
                {"part_id": "part-a", "requested_quantity": 1, "placed_quantity": 1, "remaining_quantity": 0}
            ],
            "unplaced_parts": [],
        },
    )
    job.result_path = str(result_path)
    job.artifact_path = str(result_path)
    error_path = artifact_error_path(job.id, "pdf")
    error_path.write_text("stale failure", encoding="utf-8")

    artifact_path = ensure_artifact(job, "pdf")

    assert artifact_path.exists()
    assert artifact_path.read_bytes().startswith(b"%PDF")
    assert not error_path.exists()


def test_resolve_artifact_marks_available_after_dxf_generation(app_env) -> None:
    job = _job(
        state=JobState.SUCCEEDED,
        payload={"sheet": {"units": "mm"}},
    )
    result_path = save_job_result(
        job.id,
        {
            "status": "SUCCEEDED",
            "summary": {"total_parts": 1},
            "layouts": [
                {
                    "sheet_id": "sheet-1",
                    "instance": 1,
                    "width": 100,
                    "height": 100,
                    "placements": [
                        {
                            "part_id": "part-a",
                            "x": 0,
                            "y": 0,
                            "width": 20,
                            "height": 10,
                            "polygon": {
                                "points": [
                                    {"x": 0, "y": 0},
                                    {"x": 20, "y": 0},
                                    {"x": 20, "y": 10},
                                    {"x": 0, "y": 10},
                                    {"x": 0, "y": 0}
                                ]
                            },
                        }
                    ],
                }
            ],
            "parts": [],
            "unplaced_parts": [],
        },
    )
    job.result_path = str(result_path)
    job.artifact_path = str(result_path)

    generated = ensure_artifact(job, "dxf")
    descriptor = resolve_artifact(job, "dxf")

    assert generated == artifact_store_path(job.id, "dxf")
    assert descriptor["status"] == "available"
    assert descriptor["url"] is not None
    assert descriptor["filename"].endswith(".dxf")
