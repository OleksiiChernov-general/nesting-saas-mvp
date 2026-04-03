from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import NestingJobCreateRequest


def _base_payload() -> dict[str, object]:
    return {
        "mode": "batch_quantity",
        "parts": [
            {
                "part_id": "part-a",
                "filename": "part-a.dxf",
                "quantity": 2,
                "enabled": True,
                "fill_only": False,
                "order_id": "order-a",
                "order_name": "Order A",
                "priority": 2,
                "polygon": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 40, "y": 0},
                        {"x": 40, "y": 20},
                        {"x": 0, "y": 20},
                        {"x": 0, "y": 0},
                    ]
                },
            }
        ],
        "sheet": {"sheet_id": "sheet-1", "width": 100, "height": 100, "quantity": 1, "units": "mm"},
        "batch": {
            "batch_id": "batch-alpha",
            "batch_name": "Batch Alpha",
            "orders": [{"order_id": "order-a", "order_name": "Order A", "priority": 2, "part_ids": ["part-a"]}],
        },
        "params": {"gap": 2.0, "rotation": [0, 180], "objective": "maximize_yield"},
    }


def test_batch_payload_accepts_matching_order_metadata() -> None:
    request = NestingJobCreateRequest.model_validate(_base_payload())

    assert request.batch is not None
    assert request.batch.batch_id == "batch-alpha"
    assert request.batch.orders[0].order_id == "order-a"
    assert request.parts[0].order_name == "Order A"


def test_batch_payload_rejects_priority_mismatch() -> None:
    payload = _base_payload()
    payload["batch"]["orders"][0]["priority"] = 3  # type: ignore[index]

    with pytest.raises(ValidationError) as excinfo:
        NestingJobCreateRequest.model_validate(payload)

    assert "priority 3 does not match part part-a priority 2" in str(excinfo.value)


def test_batch_payload_rejects_duplicate_part_assignment() -> None:
    payload = _base_payload()
    payload["parts"].append(  # type: ignore[union-attr]
        {
            "part_id": "part-b",
            "filename": "part-b.dxf",
            "quantity": 1,
            "enabled": True,
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
    payload["batch"]["orders"].append(  # type: ignore[index]
        {"order_id": "order-b", "order_name": "Order B", "priority": 1, "part_ids": ["part-a", "part-b"]}
    )

    with pytest.raises(ValidationError) as excinfo:
        NestingJobCreateRequest.model_validate(payload)

    assert "cannot belong to multiple batch orders" in str(excinfo.value)
