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
        assert job.payload["mode"] == "batch_quantity"
        assert job.payload["sheet"]["sheet_id"] == "sheet-1"
        assert job.payload["parts"][0]["quantity"] == 2
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

    sample_job_payload["parts"].append(
        {
            "part_id": "part-b",
            "filename": "part-b.dxf",
            "enabled": True,
            "quantity": 1,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 20, "y": 0},
                    {"x": 20, "y": 20},
                    {"x": 0, "y": 20},
                    {"x": 0, "y": 0},
                ]
            },
        }
    )

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["state"] == "SUCCEEDED"
    assert status_body["progress"] == 1.0
    assert status_body["mode"] == "batch_quantity"
    assert status_body["summary"]["total_parts"] == 2
    assert len(status_body["parts"]) == 2
    assert status_body["artifact_url"] == f"/v1/nesting/jobs/{job_id}/artifact"
    assert "successfully" in status_body["status_message"].lower()

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    assert body["yield"] > 0
    assert body["layouts"]
    assert body["mode"] == "batch_quantity"
    assert body["summary"]["total_parts"] == 2
    assert len(body["parts"]) == 2
    assert all("requested_quantity" in part for part in body["parts"])
    assert all("placed_quantity" in part for part in body["parts"])
    assert all("remaining_quantity" in part for part in body["parts"])

    artifact_response = client.get(f"/v1/nesting/jobs/{job_id}/artifact")
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"].startswith("application/json")
    assert "attachment; filename=" in artifact_response.headers["content-disposition"]
    assert artifact_response.json()["job_id"] == job_id


def test_fill_sheet_multi_part_integration_flow(client, sample_job_payload):
    sample_job_payload["mode"] = "fill_sheet"
    sample_job_payload["parts"][0]["quantity"] = None
    sample_job_payload["parts"].append(
        {
            "part_id": "part-b",
            "filename": "part-b.dxf",
            "enabled": True,
            "quantity": None,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 20, "y": 0},
                    {"x": 20, "y": 20},
                    {"x": 0, "y": 20},
                    {"x": 0, "y": 0},
                ]
            },
        }
    )

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["state"] == "SUCCEEDED"
    assert status_body["mode"] == "fill_sheet"
    assert status_body["summary"]["total_parts"] == 2

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    assert body["mode"] == "fill_sheet"
    assert body["summary"]["total_parts"] == 2
    assert len(body["parts"]) == 2
    assert all(part["placed_quantity"] > 0 for part in body["parts"])
    assert all(part["requested_quantity"] == 1 for part in body["parts"])
    assert all("placed_quantity" in part for part in body["parts"])
    assert all("remaining_quantity" in part for part in body["parts"])


def test_fill_sheet_mixed_result_shares_one_sheet_and_keeps_placing(client, sample_job_payload):
    sample_job_payload["mode"] = "fill_sheet"
    sample_job_payload["params"]["gap"] = 0.0
    sample_job_payload["parts"] = [
        {
            "part_id": "large",
            "filename": "large.dxf",
            "enabled": True,
            "quantity": None,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 10, "y": 0},
                    {"x": 10, "y": 10},
                    {"x": 0, "y": 10},
                    {"x": 0, "y": 0},
                ]
            },
        },
        {
            "part_id": "small",
            "filename": "small.dxf",
            "enabled": True,
            "quantity": None,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 5, "y": 0},
                    {"x": 5, "y": 10},
                    {"x": 0, "y": 10},
                    {"x": 0, "y": 0},
                ]
            },
        },
    ]
    sample_job_payload["sheet"] = {"sheet_id": "sheet-1", "width": 25, "height": 10, "quantity": 1, "units": "mm"}

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    placed_part_ids = [placement["part_id"] for placement in body["layouts"][0]["placements"]]
    by_part = {item["part_id"]: item for item in body["parts"]}

    assert len(body["layouts"]) == 1
    assert len(body["layouts"][0]["placements"]) == 3
    assert set(placed_part_ids) == {"large", "small"}
    assert by_part["large"]["placed_quantity"] == 2
    assert by_part["small"]["placed_quantity"] == 1
    assert body["scrap_area"] == 0


def test_fill_sheet_single_part_integration_places_many_copies(client, sample_job_payload):
    sample_job_payload["mode"] = "fill_sheet"
    sample_job_payload["parts"] = [
        {
            "part_id": "plate",
            "filename": "plate.dxf",
            "enabled": True,
            "quantity": None,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 40, "y": 0},
                    {"x": 40, "y": 25},
                    {"x": 0, "y": 25},
                    {"x": 0, "y": 0},
                ]
            },
        }
    ]
    sample_job_payload["sheet"] = {"sheet_id": "sheet-1", "width": 200, "height": 100, "quantity": 1, "units": "mm"}

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    assert body["mode"] == "fill_sheet"
    assert body["parts"][0]["placed_quantity"] == 20
    assert body["parts"][0]["remaining_quantity"] == 0
    assert body["total_parts_placed"] == 20
    assert body["yield"] == 1.0


def test_batch_quantity_single_part_integration_places_exactly_one(client, sample_job_payload):
    sample_job_payload["mode"] = "batch_quantity"
    sample_job_payload["parts"] = [
        {
            "part_id": "single",
            "filename": "single.dxf",
            "enabled": True,
            "quantity": 1,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 40, "y": 0},
                    {"x": 40, "y": 25},
                    {"x": 0, "y": 25},
                    {"x": 0, "y": 0},
                ]
            },
        }
    ]
    sample_job_payload["sheet"] = {"sheet_id": "sheet-1", "width": 200, "height": 100, "quantity": 1, "units": "mm"}

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    assert body["mode"] == "batch_quantity"
    assert body["parts"][0]["requested_quantity"] == 1
    assert body["parts"][0]["placed_quantity"] == 1
    assert body["parts"][0]["remaining_quantity"] == 0
    assert body["total_parts_placed"] == 1


def test_batch_quantity_partial_fit_integration_reports_remaining(client, sample_job_payload):
    sample_job_payload["mode"] = "batch_quantity"
    sample_job_payload["params"]["gap"] = 0.0
    sample_job_payload["parts"] = [
        {
            "part_id": "panel",
            "filename": "panel.dxf",
            "enabled": True,
            "quantity": 5,
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
    ]
    sample_job_payload["sheet"] = {"sheet_id": "sheet-1", "width": 20, "height": 20, "quantity": 1, "units": "mm"}

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    assert body["mode"] == "batch_quantity"
    assert body["parts"][0]["requested_quantity"] == 5
    assert body["parts"][0]["placed_quantity"] == 4
    assert body["parts"][0]["remaining_quantity"] == 1
    assert body["unplaced_parts"] == ["panel"]
    assert any("remaining quantity stays above zero" in warning for warning in body["warnings"])


def test_batch_quantity_multi_part_integration_handles_requested_counts_and_partial_fit(client, sample_job_payload):
    sample_job_payload["mode"] = "batch_quantity"
    sample_job_payload["params"]["gap"] = 0.0
    sample_job_payload["parts"] = [
        {
            "part_id": "large",
            "filename": "large.dxf",
            "enabled": True,
            "quantity": 1,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 12, "y": 0},
                    {"x": 12, "y": 10},
                    {"x": 0, "y": 10},
                    {"x": 0, "y": 0},
                ]
            },
        },
        {
            "part_id": "small",
            "filename": "small.dxf",
            "enabled": True,
            "quantity": 4,
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 8, "y": 0},
                    {"x": 8, "y": 10},
                    {"x": 0, "y": 10},
                    {"x": 0, "y": 0},
                ]
            },
        },
    ]
    sample_job_payload["sheet"] = {"sheet_id": "sheet-1", "width": 20, "height": 20, "quantity": 1, "units": "mm"}

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    body = result_response.json()
    by_part = {item["part_id"]: item for item in body["parts"]}

    assert body["mode"] == "batch_quantity"
    assert body["parts_placed"] == 4
    assert by_part["large"]["requested_quantity"] == 1
    assert by_part["large"]["placed_quantity"] == 1
    assert by_part["large"]["remaining_quantity"] == 0
    assert by_part["small"]["requested_quantity"] == 4
    assert by_part["small"]["placed_quantity"] == 3
    assert by_part["small"]["remaining_quantity"] == 1
    assert by_part["large"]["area_contribution"] == 120.0
    assert by_part["small"]["area_contribution"] == 240.0
    assert body["unplaced_parts"] == ["small"]


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
