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
    assert body["parts"][0]["order_id"] == "order-a"
    assert body["parts"][0]["order_name"] == "Order A"
    assert body["parts"][0]["priority"] == 2
    assert body["batch"]["batch_id"] == "batch-alpha"
    assert body["batch"]["orders"][0]["order_id"] == "order-a"
    assert body["artifact_url"] is None
    assert len(body["artifacts"]) == 3
    assert body["artifacts"][0]["kind"] == "json"
    assert body["artifacts"][0]["status"] == "processing"
    assert body["artifacts"][1]["status"] == "processing"
    assert body["queued_at"] is not None

    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(body["id"]))
        assert job is not None
        assert job.payload["mode"] == "batch_quantity"
        assert job.payload["sheet"]["units"] == "mm"
        assert job.payload["parts"][0]["quantity"] == 2
        assert job.payload["parts"][0]["order_id"] == "order-a"
        assert job.payload["batch"]["orders"][0]["order_id"] == "order-a"
        assert job.payload["engine_backend_requested"] == "python"


def test_create_job_accepts_optional_engine_backend_override(client, sample_job_payload):
    sample_job_payload["engine_backend"] = "native"

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 202
    body = response.json()
    assert body["engine_backend_requested"] == "native"

    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(body["id"]))
        assert job is not None
        assert job.payload["engine_backend_requested"] == "native"


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


def test_create_job_persists_material_payload(client, sample_job_payload):
    sample_job_payload["material"] = {
        "material_id": "preset-mild-steel-3mm",
        "name": "Mild Steel 3 mm",
        "thickness": 3.0,
        "sheet_width": 3000,
        "sheet_height": 1500,
        "units": "mm",
        "kerf": 2.0,
        "notes": "Default production steel preset.",
    }

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 202
    body = response.json()
    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(body["id"]))
        assert job is not None
        assert job.payload["material"]["material_id"] == "preset-mild-steel-3mm"
        assert job.payload["material"]["sheet_width"] == 3000
        assert job.payload["material"]["kerf"] == 2.0


def test_create_job_rejects_batch_order_with_unknown_part_reference(client, sample_job_payload):
    sample_job_payload["batch"]["orders"][0]["part_ids"] = ["missing-part"]

    response = client.post("/v1/nesting/jobs", json=sample_job_payload)

    assert response.status_code == 422
    assert "references unknown or disabled part_id" in response.text


def test_create_job_rejects_when_explicit_part_orders_are_missing_from_batch(client, sample_job_payload):
    sample_job_payload["parts"].append(
        {
            "part_id": "part-b",
            "filename": "part-b.dxf",
            "enabled": True,
            "quantity": 1,
            "order_id": "order-b",
            "order_name": "Order B",
            "priority": 1,
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

    assert response.status_code == 422
    assert "Batch metadata is missing explicit part order ids: order-b" in response.text


def test_material_endpoints_create_and_update_materials(client):
    list_response = client.get("/v1/materials")

    assert list_response.status_code == 200
    presets = list_response.json()
    assert len(presets) >= 2
    assert presets[0]["material_id"]

    create_response = client.post(
        "/v1/materials",
        json={
            "name": "Custom Aluminum",
            "thickness": 1.5,
            "sheet_width": 2000,
            "sheet_height": 1000,
            "units": "mm",
            "kerf": 1.2,
            "notes": "Created in test.",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["material_id"].startswith("material-")
    assert created["name"] == "Custom Aluminum"

    update_response = client.put(
        f"/v1/materials/{created['material_id']}",
        json={
            "material_id": created["material_id"],
            "name": "Custom Aluminum Revised",
            "thickness": 2.0,
            "sheet_width": 2100,
            "sheet_height": 1100,
            "units": "mm",
            "kerf": 1.4,
            "notes": "Updated in test.",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["material_id"] == created["material_id"]
    assert updated["name"] == "Custom Aluminum Revised"
    assert updated["sheet_width"] == 2100

    final_list = client.get("/v1/materials")
    assert any(item["material_id"] == created["material_id"] and item["name"] == "Custom Aluminum Revised" for item in final_list.json())


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
