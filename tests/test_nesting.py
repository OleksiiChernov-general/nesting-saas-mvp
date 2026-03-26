from __future__ import annotations

from shapely.geometry import Polygon

from app.nesting import PartSpec, SheetSpec, nest


def test_nesting_is_deterministic():
    parts = [PartSpec(part_id="p1", polygon=Polygon([(0, 0), (40, 0), (40, 20), (0, 20), (0, 0)]), quantity=2)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=100, height=100, quantity=1)]
    params = {"gap": 2.0, "rotation": [0, 180], "objective": "maximize_yield"}

    first = nest(parts, sheets, params)
    second = nest(parts, sheets, params)

    assert first["yield"] == second["yield"]
    assert [(p.part_id, p.x, p.y) for p in first["layouts"][0]["placements"]] == [
        (p.part_id, p.x, p.y) for p in second["layouts"][0]["placements"]
    ]


def test_nesting_respects_sheet_bounds_and_gap():
    parts = [
        PartSpec(part_id="p1", polygon=Polygon([(0, 0), (40, 0), (40, 20), (0, 20), (0, 0)]), quantity=2),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=100, height=100, quantity=1)]

    result = nest(parts, sheets, {"gap": 2.0, "rotation": [0, 180], "objective": "maximize_yield"})

    placements = result["layouts"][0]["placements"]
    assert len(placements) == 2
    assert placements[0].polygon.disjoint(placements[1].polygon)
    assert all(placement.polygon.bounds[2] <= 100 and placement.polygon.bounds[3] <= 100 for placement in placements)


def test_nesting_metrics_are_consistent_for_known_fixture():
    parts = [
        PartSpec(part_id="p1", polygon=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]), quantity=1),
        PartSpec(part_id="p2", polygon=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 2
    assert result["layouts_used"] == 1
    assert result["used_area"] == 200.0
    assert result["total_sheet_area"] == 400.0
    assert result["scrap_area"] == 200.0
    assert result["yield"] == 0.5
    assert result["yield_ratio"] == 0.5
    assert result["scrap_ratio"] == 0.5
    assert result["layouts"][0]["used_area"] == 200.0
    assert result["layouts"][0]["scrap_area"] == 200.0


def test_nesting_many_small_parts_can_fill_most_of_sheet():
    parts = [
        PartSpec(part_id="chip", polygon=Polygon([(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]), quantity=20),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 20
    assert result["used_area"] == 320.0
    assert result["yield"] == 0.8
    assert result["yield"] > 0.7


def test_nesting_rejects_part_larger_than_sheet():
    parts = [
        PartSpec(part_id="oversized", polygon=Polygon([(0, 0), (30, 0), (30, 10), (0, 10), (0, 0)]), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 0
    assert result["layouts_used"] == 0
    assert result["used_area"] == 0.0
    assert result["yield"] == 0.0
    assert result["unplaced_parts"] == ["oversized"]


def test_nesting_debug_payload_reports_geometry_and_scale():
    parts = [
        PartSpec(part_id="p1", polygon=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]), quantity=1),
        PartSpec(part_id="p2", polygon=Polygon([(0, 0), (5, 0), (5, 10), (0, 10), (0, 0)]), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"gap": 0.0, "rotation": [0], "objective": "maximize_yield", "debug": True})

    assert result["debug"]["sheet"]["width"] == 20.0
    assert result["debug"]["total_used_area"] == 150.0
    assert result["debug"]["total_scrap_area"] == 250.0
    assert len(result["debug"]["placements"]) == 2
    assert all(item["area"] > 0 for item in result["debug"]["placements"])
    assert all(item["valid"] is True for item in result["debug"]["placements"])
    assert all(item["within_sheet"] is True for item in result["debug"]["placements"])
    assert result["debug"]["scale_info"]["cluster_flagged"] is False
