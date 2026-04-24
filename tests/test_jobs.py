from __future__ import annotations

from uuid import UUID

import ezdxf
import pytest

from app.db import get_session_factory
from app.models import JobState, NestingJob
from app.native_runner import NativePOCResult, NativeRunnerError
from app.services import EngineRunTimeout, run_timeout_probe
from app.settings import get_settings
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


def test_default_backend_uses_v3_when_request_omits_engine_backend(client, sample_job_payload):
    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=5) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result_body = result_response.json()
    assert result_body["engine_backend_requested"] == "v3"
    assert result_body["engine_backend_used"] == "v3"
    assert result_body["engine_fallback_reason"] is None


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
            "order_id": "order-b",
            "order_name": "Order B",
            "priority": 1,
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
    sample_job_payload["batch"]["orders"].append(
        {"order_id": "order-b", "order_name": "Order B", "priority": 1, "part_ids": ["part-b"]}
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
    assert body["batch"]["batch_id"] == "batch-alpha"
    assert [order["order_id"] for order in body["batch"]["orders"]] == ["order-a", "order-b"]
    assert all("requested_quantity" in part for part in body["parts"])
    assert all("placed_quantity" in part for part in body["parts"])
    assert all("remaining_quantity" in part for part in body["parts"])
    assert all("order_id" in part for part in body["parts"])
    assert all("priority" in part for part in body["parts"])
    assert all("order_id" in placement for layout in body["layouts"] for placement in layout["placements"])
    placements_by_part = {
        placement["part_id"]: placement
        for layout in body["layouts"]
        for placement in layout["placements"]
    }
    assert placements_by_part["part-a"]["order_id"] == "order-a"
    assert placements_by_part["part-b"]["order_id"] == "order-b"
    assert placements_by_part["part-b"]["priority"] == 1

    artifact_response = client.get(f"/v1/nesting/jobs/{job_id}/artifact")
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"].startswith("application/json")
    assert "attachment; filename=" in artifact_response.headers["content-disposition"]
    assert artifact_response.json()["job_id"] == job_id

    dxf_response = client.get(f"/v1/nesting/jobs/{job_id}/artifact/dxf")
    assert dxf_response.status_code == 200
    assert dxf_response.headers["content-type"].startswith("application/dxf")
    assert len(dxf_response.content) > 0

    pdf_response = client.get(f"/v1/nesting/jobs/{job_id}/artifact/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF")
    assert b"Nestora PDF Report" in pdf_response.content

    assert len(body["artifacts"]) == 3
    assert body["artifacts"][0]["status"] == "available"
    assert body["artifacts"][1]["kind"] == "dxf"
    assert body["artifacts"][1]["status"] == "available"
    assert body["artifacts"][2]["status"] == "available"
    assert body["economics"]["status"] == "available"
    assert body["economics"]["material_cost"] == 25.0
    assert body["economics"]["used_material_cost"] == pytest.approx(5.0)
    assert body["economics"]["waste_cost"] == pytest.approx(20.0)
    assert body["economics"]["currency"] == "USD"
    assert body["economics"]["used_material_cost_estimated"] is True
    assert body["offcut_summary"]["approximation"] is True
    assert body["offcut_summary"]["total_leftover_area"] == pytest.approx(body["scrap_area"])
    assert body["offcut_summary"]["reusable_leftover_area"] >= 0
    assert body["offcut_summary"]["reusable_area_estimate"] == pytest.approx(body["offcut_summary"]["reusable_leftover_area"])
    assert body["offcut_summary"]["estimated_scrap_area"] >= 0
    assert isinstance(body["offcut_summary"]["leftover_summaries"], list)
    assert isinstance(body["offcuts"], list)
    assert all("bounds" in piece for piece in body["offcuts"])


def test_batch_result_preserves_explicit_order_grouping_for_multiple_orders(client, sample_job_payload):
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
    sample_job_payload["batch"] = {
        "batch_id": "batch-combined",
        "batch_name": "Combined Orders",
        "orders": [
            {"order_id": "order-a", "order_name": "Order A", "priority": 2, "part_ids": ["part-a"]},
            {"order_id": "order-b", "order_name": "Order B", "priority": 1, "part_ids": ["part-b"]},
        ],
    }

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_body = client.get(f"/v1/nesting/jobs/{job_id}").json()
    result_body = client.get(f"/v1/nesting/jobs/{job_id}/result").json()

    assert status_body["batch"]["batch_id"] == "batch-combined"
    assert [order["order_id"] for order in status_body["batch"]["orders"]] == ["order-a", "order-b"]
    assert result_body["batch"]["batch_name"] == "Combined Orders"
    assert [order["part_ids"] for order in result_body["batch"]["orders"]] == [["part-a"], ["part-b"]]
    by_part = {part["part_id"]: part for part in result_body["parts"]}
    assert by_part["part-a"]["order_id"] == "order-a"
    assert by_part["part-b"]["order_id"] == "order-b"


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
    assert body["status"] == "PARTIAL"
    assert body["parts"][0]["requested_quantity"] == 5
    assert body["parts"][0]["placed_quantity"] == 4
    assert body["parts"][0]["remaining_quantity"] == 1
    assert body["unplaced_parts"] == ["panel"]
    assert any("remaining quantity stays above zero" in warning for warning in body["warnings"])


def test_improvement_run_increments_run_number_and_keeps_history(client, sample_job_payload):
    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    first_job_id = create_response.json()["id"]
    assert process_next_job(timeout=1) is True

    first_result = client.get(f"/v1/nesting/jobs/{first_job_id}/result").json()

    improvement_payload = dict(sample_job_payload)
    improvement_payload["previous_job_id"] = first_job_id
    second_create_response = client.post("/v1/nesting/jobs", json=improvement_payload)
    second_job_id = second_create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    second_status = client.get(f"/v1/nesting/jobs/{second_job_id}").json()
    second_result = client.get(f"/v1/nesting/jobs/{second_job_id}/result").json()

    assert second_status["run_number"] == 2
    assert second_result["run_number"] == 2
    assert second_result["previous_yield"] == first_result["yield"]
    assert second_result["best_yield"] >= first_result["yield"]
    assert len(second_result["optimization_history"]) >= 1


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


def test_native_backend_falls_back_to_python_automatically(client, sample_job_payload, monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_enabled", True)

    def fake_native_runner(*args, **kwargs):
        raise NativeRunnerError("native backend smoke failure")

    monkeypatch.setattr("app.services.run_native_poc", fake_native_runner)
    sample_job_payload["engine_backend"] = "native"

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["state"] == "SUCCEEDED"
    assert status_body["engine_backend_requested"] == "native"
    assert status_body["engine_backend_used"] == "python"
    assert "native backend smoke failure" in (status_body["engine_fallback_reason"] or "")

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result_body = result_response.json()
    assert result_body["engine_backend_requested"] == "native"
    assert result_body["engine_backend_used"] == "python"
    assert "native backend smoke failure" in (result_body["engine_fallback_reason"] or "")
    assert result_body["layouts"]


def test_explicit_python_backend_routes_to_v3(client, sample_job_payload, monkeypatch: pytest.MonkeyPatch):
    # "python" is a legacy alias that now transparently routes to the v3 engine.
    native_calls = 0

    def fake_native_runner(*args, **kwargs):
        nonlocal native_calls
        native_calls += 1
        raise AssertionError("native runner should not be called for explicit python backend")

    monkeypatch.setattr("app.services.run_native_poc", fake_native_runner)
    sample_job_payload["engine_backend"] = "python"

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=5) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result_body = result_response.json()
    assert result_body["engine_backend_requested"] == "python"
    assert result_body["engine_backend_used"] == "v3"   # "python" is now a v3 alias
    assert result_body["engine_fallback_reason"] is None
    assert native_calls == 0


def test_native_backend_disabled_falls_back_to_python(client, sample_job_payload, monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_enabled", False)

    def fake_native_runner(*args, **kwargs):
        raise AssertionError("native runner should not be called while native backend is disabled")

    monkeypatch.setattr("app.services.run_native_poc", fake_native_runner)
    sample_job_payload["engine_backend"] = "native"

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["engine_backend_requested"] == "native"
    assert status_body["engine_backend_used"] == "python"
    assert "NESTING_NATIVE_POC_ENABLED is false" in (status_body["engine_fallback_reason"] or "")


def test_native_backend_without_stable_layout_payload_falls_back_to_python(client, sample_job_payload, monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_enabled", True)

    def fake_native_runner(*args, **kwargs):
        return NativePOCResult(
            status="PARSED_READY_FOR_ADAPTER",
            backend_name="summary_stub",
            backend_available=True,
            converted_part_count=1,
            placement_count=0,
            bins_used=0,
            payload={"status": "PARSED_READY_FOR_ADAPTER", "backend_available": True},
            stdout='{"status":"PARSED_READY_FOR_ADAPTER"}',
            stderr="",
            exit_code=0,
            input_digest="sha256:test",
            artifact_dir=None,
        )

    monkeypatch.setattr("app.services.run_native_poc", fake_native_runner)
    sample_job_payload["engine_backend"] = "native"

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result_body = result_response.json()
    assert result_body["engine_backend_requested"] == "native"
    assert result_body["engine_backend_used"] == "python"
    assert "stable job result payload" in (result_body["engine_fallback_reason"] or "")


def test_python_timeout_probe_terminates_synthetic_long_task() -> None:
    with pytest.raises(EngineRunTimeout) as excinfo:
        run_timeout_probe(seconds=2.0, timeout_seconds=1.0)

    assert excinfo.value.timeout_seconds == 1.0
    assert excinfo.value.engine_backend == "python"


def test_worker_timeout_is_persisted_and_leaves_no_running_job(
    client,
    sample_job_payload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "max_compute_seconds", 1.0)

    def fake_run_nesting_backend(**kwargs):
        raise EngineRunTimeout(
            "Python nesting engine timed out after 1.0s",
            engine_backend="python",
            timeout_seconds=1.0,
        )

    monkeypatch.setattr("app.services._run_nesting_backend", fake_run_nesting_backend)

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["state"] == "FAILED"
    assert status_body["timed_out"] is True
    assert status_body["error_type"] == "timeout"
    assert status_body["timeout_seconds"] == 1.0
    assert "timed out" in (status_body["status_message"] or "").lower()

    with get_session_factory()() as db:
        job = db.get(NestingJob, UUID(job_id))
        assert job is not None
        assert job.state == JobState.FAILED
        assert job.finished_at is not None
        assert job.heartbeat_at is not None
        assert job.state != JobState.RUNNING
