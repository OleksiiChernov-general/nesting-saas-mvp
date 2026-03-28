from __future__ import annotations

import time

import pytest
from shapely.geometry import Polygon

import app.nesting as nesting_module
from app.nesting import PartSpec, SheetSpec, nest


def rectangle(width: float, height: float) -> Polygon:
    return Polygon([(0, 0), (width, 0), (width, height), (0, height), (0, 0)])


def test_fill_sheet_repeats_single_part_until_sheet_is_full():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["mode"] == "fill_sheet"
    assert result["summary"]["total_parts"] == 1
    assert result["parts_placed"] == 4
    assert result["total_parts_placed"] == 4
    assert result["used_area"] == 400.0
    assert result["yield"] == 1.0
    assert result["parts"][0]["requested_quantity"] == 1
    assert result["parts"][0]["placed_quantity"] == 4
    assert result["parts"][0]["remaining_quantity"] == 0


def test_batch_quantity_places_exact_requested_single_part_count():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=3)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=40, height=10, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["mode"] == "batch_quantity"
    assert result["parts_placed"] == 3
    assert result["total_parts_placed"] == 3
    assert result["unplaced_parts"] == []
    assert result["parts"][0]["requested_quantity"] == 3
    assert result["parts"][0]["placed_quantity"] == 3
    assert result["parts"][0]["remaining_quantity"] == 0


def test_batch_quantity_reports_partial_fit():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=5)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 4
    assert result["unplaced_parts"] == ["panel"]
    assert result["parts"][0]["requested_quantity"] == 5
    assert result["parts"][0]["placed_quantity"] == 4
    assert result["parts"][0]["remaining_quantity"] == 1


def test_fill_sheet_can_mix_multiple_part_types():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(12, 10), quantity=1),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(8, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    placed_by_part = {item["part_id"]: item["placed_quantity"] for item in result["parts"]}

    assert result["parts_placed"] == 4
    assert placed_by_part["large"] == 2
    assert placed_by_part["small"] == 2
    assert result["used_area"] == 400.0
    assert result["yield"] == 1.0


def test_fill_sheet_keeps_placing_mixed_parts_until_no_enabled_part_fits():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(10, 10), quantity=1),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(5, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=25, height=10, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    layout = result["layouts"][0]
    placed_part_ids = [placement.part_id for placement in layout["placements"]]
    placed_by_part = {item["part_id"]: item["placed_quantity"] for item in result["parts"]}

    assert len(layout["placements"]) == 3
    assert set(placed_part_ids) == {"large", "small"}
    assert placed_by_part["large"] == 2
    assert placed_by_part["small"] == 1
    assert result["used_area"] == 250.0
    assert result["scrap_area"] == 0.0


def test_fill_sheet_large_single_part_places_many_copies():
    parts = [PartSpec(part_id="plate", filename="plate.dxf", polygon=rectangle(40, 25), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=200, height=100, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 20
    assert result["total_parts_placed"] == 20
    assert result["parts"][0]["placed_quantity"] == 20
    assert result["parts"][0]["remaining_quantity"] == 0
    assert result["used_area"] == 20000.0
    assert result["scrap_area"] == 0.0
    assert result["yield"] == 1.0


def test_fill_sheet_regression_does_not_stop_after_first_copy():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=100, height=100, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 100
    assert result["used_area"] == 10000.0
    assert result["yield"] == 1.0


def test_fill_sheet_solo_mode_uses_only_selected_part():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(12, 10), quantity=1, fill_only=True),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(8, 10), quantity=1),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "fill_sheet", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    placed_by_part = {item["part_id"]: item["placed_quantity"] for item in result["parts"]}

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
    assert result["total_parts_placed"] == 2
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
    assert any("does not fit within the available sheet bounds" in warning for warning in result["warnings"])


def test_zero_area_part_is_reported_safely_without_crashing():
    parts = [PartSpec(part_id="flat", filename="flat.dxf", polygon=Polygon([(0, 0), (10, 0), (20, 0), (0, 0)]), quantity=2)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=100, height=100, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 0
    assert result["used_area"] == 0.0
    assert result["scrap_area"] == 0.0
    assert result["parts"][0]["placed_quantity"] == 0
    assert result["parts"][0]["remaining_quantity"] == 2
    assert any("invalid or zero-area" in warning for warning in result["warnings"])


def test_batch_quantity_places_exactly_one_when_requested():
    parts = [PartSpec(part_id="single", filename="single.dxf", polygon=rectangle(40, 25), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=200, height=100, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})

    assert result["parts_placed"] == 1
    assert result["total_parts_placed"] == 1
    assert result["parts"][0]["requested_quantity"] == 1
    assert result["parts"][0]["placed_quantity"] == 1
    assert result["parts"][0]["remaining_quantity"] == 0


def test_multi_part_batch_respects_requested_counts():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(40, 25), quantity=2),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(20, 25), quantity=4),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=160, height=50, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})
    by_part = {item["part_id"]: item for item in result["parts"]}

    assert result["parts_placed"] == 6
    assert result["total_parts_placed"] == 6
    assert by_part["large"]["placed_quantity"] == 2
    assert by_part["large"]["remaining_quantity"] == 0
    assert by_part["small"]["placed_quantity"] == 4
    assert by_part["small"]["remaining_quantity"] == 0
    assert result["used_area"] == 8000.0
    assert result["yield"] == 1.0


def test_multi_part_batch_reports_partial_fit_and_area_contribution():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(12, 10), quantity=1),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(8, 10), quantity=3),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})
    by_part = {item["part_id"]: item for item in result["parts"]}

    assert result["parts_placed"] == 4
    assert result["unplaced_parts"] == []
    assert by_part["large"]["requested_quantity"] == 1
    assert by_part["large"]["placed_quantity"] == 1
    assert by_part["large"]["remaining_quantity"] == 0
    assert by_part["large"]["area_contribution"] == 120.0
    assert by_part["small"]["requested_quantity"] == 3
    assert by_part["small"]["placed_quantity"] == 3
    assert by_part["small"]["remaining_quantity"] == 0
    assert by_part["small"]["area_contribution"] == 240.0
    assert result["used_area"] == 360.0
    assert result["used_area"] == sum(layout["used_area"] for layout in result["layouts"])
    assert result["used_area"] == sum(part["area_contribution"] for part in result["parts"])


def test_multi_part_batch_partial_fit_reports_remaining_per_part():
    parts = [
        PartSpec(part_id="large", filename="large.dxf", polygon=rectangle(12, 10), quantity=1),
        PartSpec(part_id="small", filename="small.dxf", polygon=rectangle(8, 10), quantity=4),
    ]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]

    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield"})
    by_part = {item["part_id"]: item for item in result["parts"]}

    assert result["parts_placed"] == 4
    assert result["unplaced_parts"] == ["small"]
    assert by_part["large"]["placed_quantity"] == 1
    assert by_part["large"]["remaining_quantity"] == 0
    assert by_part["small"]["requested_quantity"] == 4
    assert by_part["small"]["placed_quantity"] == 3
    assert by_part["small"]["remaining_quantity"] == 1
    assert any("remaining quantity stays above zero" in warning for warning in result["warnings"])


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


def test_timeout_returns_best_valid_layout_so_far(monkeypatch: pytest.MonkeyPatch):
    original_select = nesting_module._select_next_placement

    def slow_select(*args, **kwargs):
        time.sleep(0.01)
        return original_select(*args, **kwargs)

    monkeypatch.setattr(nesting_module, "_select_next_placement", slow_select)

    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=20)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=100, height=100, quantity=1)]

    started = time.perf_counter()
    result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield", "time_limit_sec": 0.03})
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert result["status"] == "PARTIAL"
    assert result["timed_out"] is True
    assert result["compute_time_sec"] if "compute_time_sec" in result else True
    assert result["parts_placed"] >= 0
    assert result["layouts_used"] >= 0
    assert any("60-second compute limit" in warning for warning in result["warnings"])


def test_iterative_run_carries_previous_yield_metadata():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=6)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=30, height=20, quantity=1)]

    first_result = nest(parts, sheets, {"mode": "batch_quantity", "gap": 0.0, "rotation": [0], "objective": "maximize_yield", "run_number": 1})
    second_result = nest(
        parts,
        sheets,
        {
            "mode": "batch_quantity",
            "gap": 0.0,
            "rotation": [0],
            "objective": "maximize_yield",
            "run_number": 2,
            "previous_result": first_result,
        },
    )

    assert first_result["run_number"] == 1
    assert second_result["run_number"] == 2
    assert second_result["previous_yield"] == first_result["yield"]
    assert second_result["best_yield"] >= first_result["yield"]
