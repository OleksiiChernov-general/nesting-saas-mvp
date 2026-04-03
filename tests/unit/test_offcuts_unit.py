from __future__ import annotations

from shapely.geometry import box

from app.offcuts import summarize_job_offcuts, summarize_sheet_offcuts


def test_summarize_sheet_offcuts_returns_full_sheet_when_empty(app_env) -> None:
    offcuts, summary = summarize_sheet_offcuts(
        sheet_id="sheet-1",
        instance=1,
        sheet_width=100,
        sheet_height=50,
        used_area=0,
        scrap_area=5000,
        placement_polygons=[],
    )

    assert len(offcuts) == 1
    assert offcuts[0]["source"] == "empty_sheet"
    assert summary["reusable_leftover_area"] == 5000
    assert summary["estimated_scrap_area"] == 0
    assert summary["approximation_method"] == "full_sheet_rectangle"


def test_summarize_job_offcuts_reports_reusable_and_estimated_scrap(app_env) -> None:
    layouts = [
        {
            "sheet_id": "sheet-1",
            "instance": 1,
            "width": 100.0,
            "height": 50.0,
            "used_area": 1200.0,
            "scrap_area": 3800.0,
            "placements": [type("PlacementStub", (), {"polygon": box(10, 10, 40, 50)})()],
        }
    ]

    offcuts, summary = summarize_job_offcuts(layouts)

    assert offcuts
    assert summary["total_leftover_area"] == 3800.0
    assert summary["reusable_leftover_area"] > 0
    assert summary["estimated_scrap_area"] >= 0
    assert summary["reusable_area_estimate"] == summary["reusable_leftover_area"]
    assert summary["leftover_summaries"][0]["approximate"] is True
