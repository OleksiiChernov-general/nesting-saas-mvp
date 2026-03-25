from __future__ import annotations


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
    assert body["artifact_url"] is None
    assert body["queued_at"] is not None
