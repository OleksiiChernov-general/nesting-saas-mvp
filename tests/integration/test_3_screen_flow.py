from __future__ import annotations

from app.worker import process_next_job


def test_backend_3_screen_flow_contract_smoke(client, sample_job_payload) -> None:
    import_response = client.post(
        "/v1/geometry/clean",
        json={
            "polygons": [sample_job_payload["parts"][0]["polygon"]],
            "tolerance": 0.5,
        },
    )
    assert import_response.status_code == 200
    assert import_response.json()["polygons"]

    create_response = client.post("/v1/nesting/jobs", json=sample_job_payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert process_next_job(timeout=1) is True

    status_response = client.get(f"/v1/nesting/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "SUCCEEDED"

    result_response = client.get(f"/v1/nesting/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result = result_response.json()

    assert result["mode"] == "batch_quantity"
    assert result["artifacts"]
    assert result["offcut_summary"]["approximation"] is True
    assert result["economics"]["status"] in {"available", "placeholder"}
    assert result["batch"]["orders"][0]["order_id"] == "order-a"
