from __future__ import annotations

from shapely.geometry import Polygon

from app.nesting import PartSpec, SheetSpec, nest


def rectangle(width: float, height: float) -> Polygon:
    return Polygon([(0, 0), (width, 0), (width, height), (0, height), (0, 0)])


def test_fill_sheet_repeats_single_part_until_sheet_is_full():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["mode"] == "fill_sheet"
    assert result["parts_placed"] == 4
    assert result["used_area"] == 400.0
    assert result["yield"] == 1.0
    assert result["part_summaries"][0]["placed_quantity"] == 4


def test_batch_quantity_places_exact_requested_single_part_count():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=3)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=40, height=10, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["mode"] == "batch_quantity"
    assert result["parts_placed"] == 3
    assert result["unplaced_parts"] == []
    assert result["part_summaries"][0]["requested_quantity"] == 3
    assert result["part_summaries"][0]["placed_quantity"] == 3
    assert result["part_summaries"][0]["remaining_quantity"] == 0


def test_batch_quantity_reports_partial_fit():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=5)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 4
    assert result["unplaced_parts"] == ["panel"]
    assert result["part_summaries"][0]["requested_quantity"] == 5
    assert result["part_summaries"][0]["placed_quantity"] == 4
    assert result["part_summaries"][0]["remaining_quantity"] == 1


def test_fill_sheet_can_mix_multiple_part_types():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(12, 10), quantity=1),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(8, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    placed_by_part = {item["part_id"]: item["placed_quantity"] for item in result["part_summaries"]}

    assert result["parts_placed"] == 4
    assert placed_by_part["large"] == 2
    assert placed_by_part["small"] == 2
    assert result["used_area"] == 400.0
    assert result["yield"] == 1.0


def test_fill_sheet_solo_mode_uses_only_selected_part():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(12, 10), quantity=1, fill_only=True),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(8, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    placed_by_part = {item["part_id"]: item["placed_quantity"] for item in result["part_summaries"]}

    assert placed_by_part["large"] == 2
    assert placed_by_part["small"] == 0
    assert result["parts_placed"] == 2


def test_nesting_metrics_are_consistent_for_known_fixture():
    parts = [
        PartSpec(part_id="p1", filename="p1.dxf", polygon=rectangle(10, 10), quantity=1),
        PartSpec(part_id="p2", filename="p2.dxf", polygon=rectangle(5, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 2
    assert result["layouts_used"] == 1
    assert result["used_area"] == 150.0
    assert result["total_sheet_area"] == 400.0
    assert result["scrap_area"] == 250.0
    assert result["yield"] == 0.375
    assert result["yield_ratio"] == 0.375
    assert result["scrap_ratio"] == 0.625


def test_nesting_rejects_part_larger_than_sheet():
    parts = [PartSpec(part_id="oversized", filename="oversized.dxf", polygon=rectangle(30, 10), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 0
    assert result["layouts_used"] == 0
    assert result["used_area"] == 0.0
    assert result["yield"] == 0.0
    assert result["unplaced_parts"] == ["oversized"]


def test_nesting_debug_payload_reports_geometry_and_scale():
    parts = [
        PartSpec(part_id="p1", filename="p1.dxf", polygon=rectangle(10, 10), quantity=1),
        PartSpec(part_id="p2", filename="p2.dxf", polygon=rectangle(5, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(
        parts,
        sheets,
        {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield", "debug": True},
    )

    assert result["debug"]["sheet"]["width"] == 20.0
    assert result["debug"]["total_used_area"] == 150.0
    assert result["debug"]["total_scrap_area"] == 250.0
    assert len(result["debug"]["placements"]) == 2
    assert all(item["area"] > 0 for item in result["debug"]["placements"])
    assert all(item["valid"] is True for item in result["debug"]["placements"])
    assert all(item["within_sheet"] is True for item in result["debug"]["placements"])
    assert result["debug"]["scale_info"]["cluster_flagged"] is False


def test_nesting_warns_about_probable_units_mismatch():
    parts = [PartSpec(part_id="mandala", filename="mandala.dxf", polygon=rectangle(7, 7), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=1000, height=1000, quantity=1)]

    result = nest(
        parts,
        sheets,
        {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield", "source_units": "Inches", "source_max_extent": 7.0},
    )

    assert result["parts_placed"] >= 1
    assert result["warnings"]
    assert any("Possible scale mismatch" in warning for warning in result["warnings"])
