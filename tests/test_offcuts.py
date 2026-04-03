from shapely.geometry import box

from app.offcuts import summarize_job_offcuts


def test_summarize_job_offcuts_includes_compatibility_leftover_keys():
    layouts = [
        {
            "sheet_id": "sheet-1",
            "instance": 1,
            "width": 100.0,
            "height": 50.0,
            "used_area": 1200.0,
            "scrap_area": 3800.0,
            "placements": [
                type("PlacementStub", (), {"polygon": box(10, 10, 40, 50)})(),
            ],
        }
    ]

    offcuts, summary = summarize_job_offcuts(layouts)

    assert isinstance(offcuts, list)
    assert summary["total_leftover_area"] == 3800.0
    assert summary["reusable_area_estimate"] == summary["reusable_leftover_area"]
    assert summary["approximation"] is True
    assert isinstance(summary["leftover_summaries"], list)
    assert summary["leftover_summaries"]
    first = summary["leftover_summaries"][0]
    assert set(first) >= {"sheet_id", "instance", "width", "height", "area", "approximate", "source"}
    assert first["approximate"] is True
    assert first["area"] > 0
