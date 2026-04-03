from __future__ import annotations

from app.economics import build_economic_metrics


def test_build_economic_metrics_returns_available_values_with_estimates() -> None:
    economics = build_economic_metrics(
        {
            "name": "Steel",
            "sheet_width": 100,
            "sheet_height": 50,
            "cost_per_sheet": 40,
            "currency": "USD",
        },
        {
            "total_sheet_area": 5000,
            "used_area": 3000,
            "scrap_area": 2000,
            "layouts_used": 1,
            "offcut_summary": {"reusable_leftover_area": 750},
        },
    )

    assert economics["status"] == "available"
    assert economics["material_cost"] == 40.0
    assert economics["used_material_cost"] == 24.0
    assert economics["waste_cost"] == 16.0
    assert economics["savings_percent"] == 15.0
    assert economics["currency"] == "USD"
    assert economics["used_material_cost_estimated"] is True
    assert economics["waste_cost_estimated"] is True
    assert economics["savings_percent_estimated"] is True


def test_build_economic_metrics_returns_placeholder_without_cost_input() -> None:
    economics = build_economic_metrics(
        {
            "name": "Steel",
            "sheet_width": 100,
            "sheet_height": 50,
            "currency": "USD",
        },
        {
            "total_sheet_area": 5000,
            "used_area": 3000,
            "scrap_area": 2000,
        },
    )

    assert economics["status"] == "placeholder"
    assert economics["material_cost"] is None
    assert economics["used_material_cost"] is None
    assert "per-sheet material cost" in str(economics["message"])
