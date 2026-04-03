from __future__ import annotations

from uuid import uuid4

from app.artifacts import resolve_artifact
from app.models import JobState, NestingJob
from app.storage import save_job_result


def _job(*, state: JobState, artifact_path: str | None = None, result_path: str | None = None) -> NestingJob:
    return NestingJob(
        id=uuid4(),
        state=state,
        payload={},
        result_path=result_path,
        artifact_path=artifact_path,
        progress=1.0 if state in {JobState.SUCCEEDED, JobState.PARTIAL} else 0.0,
    )


def test_json_artifact_is_processing_for_running_job(app_env) -> None:
    descriptor = resolve_artifact(_job(state=JobState.RUNNING), "json")

    assert descriptor["status"] == "processing"
    assert "will be available" in descriptor["message"].lower()


def test_json_artifact_is_failed_for_finished_job_without_file(app_env) -> None:
    descriptor = resolve_artifact(_job(state=JobState.SUCCEEDED), "json")

    assert descriptor["status"] == "failed"
    assert "file is missing" in descriptor["message"].lower()


def test_dxf_artifact_is_available_for_finished_job_with_layouts(app_env) -> None:
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

    descriptor = resolve_artifact(job, "dxf")

    assert descriptor["status"] == "available"
    assert descriptor["filename"].endswith(".dxf")
