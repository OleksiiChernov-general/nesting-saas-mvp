from __future__ import annotations

from uuid import UUID

import ezdxf

from app.db import get_session_factory
from app.models import JobState, NestingJob
from app.worker import process_next_job


def test_worker_processes_job(client, sample_job_payload):
    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.json()["state"] == "QUEUED"
    job_id = create_response.json()["id"]

    processed = process_next_job(timeout=1)

    assert processed is True
    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(job_id))
        assert job is not None
        assert job.state == JobState.SUCCEEDED
        assert job.result_path is not None
        assert job.artifact_path is not None
        assert job.progress == 1.0
        assert job.status_message is not None
        assert job.started_at is not None
        assert job.finished_at is not None


def test_full_integration_flow(client, tmp_path, sample_job_payload):
    dxf_path = tmp_path / "shape.dxf"
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_line((10, 10), (0, 10))
    msp.add_line((0, 10), (0, 0))
    doc.saveas(dxf_path)

    with dxf_path.open("rb") as handle:
        import_response = client.post("/v1/files/import", files={"file": ("shape.dxf", handle, "application/dxf")})
    assert import_response.status_code == 200

    clean_response = client.post(
        "/v1/geometry/clean",
        json={
            "polygons": [
                {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 40, "y": 0},
                        {"x": 40, "y": 20},
                        {"x": 0, "y": 20},
                        {"x": 0, "y": 0},
                    ]
                }
            ],
            "tolerance": 0.5,
        },
    )
    assert clean_response.status_code == 200
    assert clean_response.json()["polygons"]

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["state"] == "SUCCEEDED"
    assert status_body["progress"] == 1.0
    assert status_body["artifact_url"] == f"/v1/nesting/jobs/{job_id}/artifact"
    assert "successfully" in status_body["status_message"].lower()

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    assert body["yield"] > 0
    assert body["layouts"]

    artifact_response = client.get(f"/v1/nesting/jobs/{job_id}/artifact")
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"].startswith("application/json")
    assert "attachment; filename=" in artifact_response.headers["content-disposition"]
    assert artifact_response.json()["job_id"] == job_id


def test_worker_failure_is_persisted(client, sample_job_payload):
    sample_job_payload["parts"][0]["polygon"]["points"] = [
        {"x": 0, "y": 0},
        {"x": 5, "y": 5},
        {"x": 10, "y": 10},
        {"x": 0, "y": 0},
    ]
    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(job_id))
        assert job is not None
        assert job.state == JobState.FAILED
        assert job.error
        assert job.finished_at is not None
        assert job.progress <= 0.95
