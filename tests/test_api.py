from __future__ import annotations

from uuid import UUID

from app.db import get_session_factory
from app.models import NestingJob


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job(client, sample_job_payload):
    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "QUEUED"
    assert body["progress"] == 0.05
    assert body["status_message"] == "Job queued for worker execution."
    assert body["error"] is None
    assert body["mode"] == "batch_quantity"
    assert body["summary"] == {"total_parts": 1}
    assert body["parts"][0]["requested_quantity"] == 2
    assert body["parts"][0]["placed_quantity"] == 0
    assert body["parts"][0]["remaining_quantity"] == 2
    assert body["artifact_url"] is None
    assert body["queued_at"] is not None

    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(body["id"]))
        assert job is not None
        assert job.payload["mode"] == "batch_quantity"
        assert job.payload["sheet"]["units"] == "mm"
        assert job.payload["parts"][0]["quantity"] == 2


def test_create_job_accepts_new_multi_part_sheet_contract(client, sample_job_payload):
    sample_job_payload["parts"].append(
        {
            "part_id": "part-b",
            "filename": "part-b.dxf",
            "enabled": True,
            "quantity": 4,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 10, "y": 0},
                    {"x": 10, "y": 10},
                    {"x": 0, "y": 10},
                    {"x": 0, "y": 0},
                ]
            },
        }
    )

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 202
    body = response.json()
    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(body["id"]))
        assert job is not None
        assert len(job.payload["parts"]) == 2
        assert job.payload["sheet"]["width"] == 100
        assert len(job.payload["sheets"]) == 1


def test_create_job_rejects_when_no_enabled_parts_are_present(client, sample_job_payload):
    sample_job_payload["parts"][0]["enabled"] = False

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 422
    assert "At least one enabled part is required" in response.text


def test_create_job_rejects_batch_quantity_without_enabled_part_quantity(client, sample_job_payload):
    sample_job_payload["parts"][0]["quantity"] = None

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 422
    assert "Batch Quantity mode requires quantity >= 1" in response.text


def test_create_job_allows_fill_sheet_without_quantity(client, sample_job_payload):
    sample_job_payload["mode"] = "fill_sheet"
    sample_job_payload["parts"][0]["quantity"] = None

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 202
