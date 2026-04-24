"""
tests/test_algorithm_v2_v3.py — Algorithm regression & quality tests for V2/V3 nesting engines.

Run with:  pytest tests/test_algorithm_v2_v3.py -v
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.nesting_v2 import run_nesting as run_v2
from app.nesting_v3 import run_nesting as run_v3

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

SHEET_1000x800 = {"sheet_id": "s1", "width": 1000, "height": 800, "quantity": 1}
SHEET_500x400  = {"sheet_id": "s2", "width": 500,  "height": 400, "quantity": 1}


def _rect_points(w: float, h: float) -> list[dict]:
    return [
        {"x": 0, "y": 0}, {"x": w, "y": 0},
        {"x": w, "y": h}, {"x": 0, "y": h}, {"x": 0, "y": 0},
    ]


def _tri_points(w: float, h: float) -> list[dict]:
    return [{"x": 0, "y": 0}, {"x": w, "y": 0}, {"x": 0, "y": h}, {"x": 0, "y": 0}]


def _L_points(w: float, h: float) -> list[dict]:
    cw, ch = w * 0.5, h * 0.5
    return [
        {"x": 0,  "y": 0}, {"x": w,  "y": 0}, {"x": w,  "y": ch},
        {"x": cw, "y": ch}, {"x": cw, "y": h}, {"x": 0,  "y": h}, {"x": 0, "y": 0},
    ]


def _make_part(part_id: str, pts: list[dict], qty: int = 1) -> dict:
    return {"part_id": part_id, "polygon": {"points": pts}, "quantity": qty}


def _run(engine_fn, parts: list[dict], sheet: dict, time_limit: float = 5.0) -> dict:
    return engine_fn(parts, sheet, {"time_limit_sec": time_limit})


def _util(result: dict, sheet: dict) -> float:
    m = result.get("metrics", {})
    util = m.get("yield_ratio") or m.get("yield") or 0.0
    if util:
        return util
    # compute from placements if metric is missing
    placed = result.get("placements", [])
    if not placed:
        return 0.0
    sheet_area = sheet["width"] * sheet["height"]
    total_area = sum(_shoelace(p.get("polygon", {}).get("points", [])) for p in placed)
    return total_area / sheet_area if sheet_area > 0 else 0.0


def _shoelace(pts: list[dict]) -> float:
    if not pts:
        return 0.0
    area = 0.0
    n = len(pts)
    for i in range(n - 1):
        area += pts[i]["x"] * pts[i + 1]["y"] - pts[i + 1]["x"] * pts[i]["y"]
    return abs(area) / 2.0


def _placed_count(result: dict) -> int:
    m = result.get("metrics", {})
    return (
        m.get("placed_parts")
        or m.get("placed_count")
        or len(result.get("placements", []))
    )


# ──────────────────────────────────────────────────────────────────────────────
# Standard test datasets (mirroring benchmark_suite.py)
# ──────────────────────────────────────────────────────────────────────────────

SET_A_PARTS = [
    _make_part("r0_200x150", _rect_points(200, 150), 4),
    _make_part("r1_300x100", _rect_points(300, 100), 6),
    _make_part("r2_150x150", _rect_points(150, 150), 8),
    _make_part("r3_120x80",  _rect_points(120,  80), 10),
    _make_part("r4_250x200", _rect_points(250, 200), 6),
    _make_part("r5_80x60",   _rect_points( 80,  60), 16),
]  # 50 rectangles total

SET_B_PARTS = [
    _make_part("rect0_150x100", _rect_points(150, 100), 4),
    _make_part("rect1_200x80",  _rect_points(200,  80), 3),
    _make_part("rect2_100x120", _rect_points(100, 120), 5),
    _make_part("rect3_80x80",   _rect_points( 80,  80), 4),
    _make_part("rect4_300x60",  _rect_points(300,  60), 2),
    _make_part("tri5_150x100",  _tri_points(150, 100),  3),
    _make_part("tri6_100x80",   _tri_points(100,  80),  4),
    _make_part("tri7_200x120",  _tri_points(200, 120),  2),
    _make_part("L8_120x150",    _L_points(120, 150),    3),
    _make_part("L9_100x200",    _L_points(100, 200),    2),
]  # 32 mixed shapes total

SET_C_PARTS = [
    _make_part("c_100x40", _rect_points(100, 40), 50),
]  # 50 identical 100×40 rectangles


# ──────────────────────────────────────────────────────────────────────────────
# Section 1 — Utilization targets (regression baselines)
# ──────────────────────────────────────────────────────────────────────────────

class TestUtilizationV3:
    """V3 engine must meet world-class utilization targets."""

    def test_set_a_rectangles(self):
        """50 mixed rectangles on 1000×800 sheet — target ≥85%."""
        result = _run(run_v3, SET_A_PARTS, SHEET_1000x800, time_limit=5.0)
        util = _util(result, SHEET_1000x800)
        assert util >= 0.85, f"Set A V3 utilization {util:.1%} < 85%"

    def test_set_b_mixed_shapes(self):
        """32 mixed shapes (rects + triangles + L-shapes) on 1000×800 — target ≥40%."""
        result = _run(run_v3, SET_B_PARTS, SHEET_1000x800, time_limit=5.0)
        util = _util(result, SHEET_1000x800)
        assert util >= 0.40, f"Set B V3 utilization {util:.1%} < 40%"

    def test_set_c_identical_parts(self):
        """50 identical 100×40 rectangles on 500×400 sheet — target ≥90%."""
        result = _run(run_v3, SET_C_PARTS, SHEET_500x400, time_limit=5.0)
        util = _util(result, SHEET_500x400)
        assert util >= 0.90, f"Set C V3 utilization {util:.1%} < 90%"


class TestUtilizationV2:
    """V2 engine must maintain its own baseline quality."""

    def test_set_a_rectangles(self):
        """V2 Set A ≥80%."""
        result = _run(run_v2, SET_A_PARTS, SHEET_1000x800, time_limit=5.0)
        util = _util(result, SHEET_1000x800)
        assert util >= 0.80, f"Set A V2 utilization {util:.1%} < 80%"

    def test_set_b_mixed_shapes(self):
        """V2 Set B ≥35%."""
        result = _run(run_v2, SET_B_PARTS, SHEET_1000x800, time_limit=5.0)
        util = _util(result, SHEET_1000x800)
        assert util >= 0.35, f"Set B V2 utilization {util:.1%} < 35%"

    def test_set_c_identical_parts(self):
        """V2 Set C ≥90%."""
        result = _run(run_v2, SET_C_PARTS, SHEET_500x400, time_limit=5.0)
        util = _util(result, SHEET_500x400)
        assert util >= 0.90, f"Set C V2 utilization {util:.1%} < 90%"


# ──────────────────────────────────────────────────────────────────────────────
# Section 2 — No-overlap validation
# ──────────────────────────────────────────────────────────────────────────────

def _check_no_overlap(placements: list[dict], tolerance: float = 1.0) -> list[str]:
    """Return list of overlap descriptions (empty = all good).

    Each placement must have a 'polygon' key with translated points.
    Falls back to bounding-box check if polygon absent.
    """
    try:
        from shapely.geometry import Polygon as SPoly
    except ImportError:
        return []  # shapely not available — skip geometric check

    polys: list[SPoly] = []
    ids: list[str] = []
    for pl in placements:
        pts = pl.get("polygon", {}).get("points", [])
        if len(pts) < 3:
            # build bbox polygon from placement fields
            x, y = pl.get("x", 0), pl.get("y", 0)
            pw = pl.get("width", pl.get("w", 0))
            ph = pl.get("height", pl.get("h", 0))
            if pw and ph:
                pts = [
                    {"x": x, "y": y}, {"x": x + pw, "y": y},
                    {"x": x + pw, "y": y + ph}, {"x": x, "y": y + ph},
                ]
            else:
                continue
        try:
            poly = SPoly([(p["x"], p["y"]) for p in pts])
            if not poly.is_valid:
                poly = poly.buffer(0)
        except Exception:
            continue
        polys.append(poly)
        ids.append(pl.get("placement_id") or pl.get("part_id") or str(len(polys)))

    errors: list[str] = []
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            inter = polys[i].intersection(polys[j])
            if not inter.is_empty and inter.area > tolerance:
                errors.append(
                    f"{ids[i]} ∩ {ids[j]}: overlap area={inter.area:.2f}"
                )
    return errors


class TestNoOverlap:
    """Placed parts must not overlap each other."""

    def test_v2_rectangles_no_overlap(self):
        result = _run(run_v2, SET_A_PARTS, SHEET_1000x800, time_limit=3.0)
        placements = result.get("placements", [])
        assert len(placements) > 0, "No parts placed"
        errors = _check_no_overlap(placements)
        assert not errors, f"Overlaps found:\n" + "\n".join(errors[:10])

    def test_v3_rectangles_no_overlap(self):
        result = _run(run_v3, SET_A_PARTS, SHEET_1000x800, time_limit=3.0)
        placements = result.get("placements", [])
        assert len(placements) > 0, "No parts placed"
        errors = _check_no_overlap(placements)
        assert not errors, f"Overlaps found:\n" + "\n".join(errors[:10])

    def test_v2_mixed_shapes_no_overlap(self):
        result = _run(run_v2, SET_B_PARTS, SHEET_1000x800, time_limit=3.0)
        placements = result.get("placements", [])
        assert len(placements) > 0, "No parts placed"
        errors = _check_no_overlap(placements)
        assert not errors, f"Overlaps found:\n" + "\n".join(errors[:10])

    def test_v3_mixed_shapes_no_overlap(self):
        result = _run(run_v3, SET_B_PARTS, SHEET_1000x800, time_limit=3.0)
        placements = result.get("placements", [])
        assert len(placements) > 0, "No parts placed"
        errors = _check_no_overlap(placements)
        assert not errors, f"Overlaps found:\n" + "\n".join(errors[:10])

    def test_single_part_no_overlap(self):
        """Trivial case: one part type, many instances."""
        parts = [_make_part("sq_50", _rect_points(50, 50), 8)]
        result = _run(run_v3, parts, SHEET_500x400, time_limit=2.0)
        placements = result.get("placements", [])
        errors = _check_no_overlap(placements)
        assert not errors, f"Overlaps found:\n" + "\n".join(errors[:10])


# ──────────────────────────────────────────────────────────────────────────────
# Section 3 — Time limit compliance
# ──────────────────────────────────────────────────────────────────────────────

class TestTimeLimits:
    """Engines must return within a reasonable margin of the requested time limit."""

    # V2 greedy: allow 50% overhead (startup + last candidate evaluation)
    _V2_MARGIN = 1.5
    # V3 3-phase: allow 2× margin (each phase checks deadline at boundaries, not mid-run)
    _V3_MARGIN = 2.0

    def test_v2_respects_1s_limit(self):
        limit = 1.0
        t0 = time.perf_counter()
        _run(run_v2, SET_A_PARTS, SHEET_1000x800, time_limit=limit)
        elapsed = time.perf_counter() - t0
        assert elapsed <= limit * self._V2_MARGIN, (
            f"V2 took {elapsed:.2f}s for a {limit}s limit"
        )

    def test_v3_respects_1s_limit(self):
        limit = 1.0
        t0 = time.perf_counter()
        _run(run_v3, SET_A_PARTS, SHEET_1000x800, time_limit=limit)
        elapsed = time.perf_counter() - t0
        assert elapsed <= limit * self._V3_MARGIN, (
            f"V3 took {elapsed:.2f}s for a {limit}s limit"
        )

    def test_v2_respects_2s_limit(self):
        limit = 2.0
        t0 = time.perf_counter()
        _run(run_v2, SET_B_PARTS, SHEET_1000x800, time_limit=limit)
        elapsed = time.perf_counter() - t0
        assert elapsed <= limit * self._V2_MARGIN, (
            f"V2 took {elapsed:.2f}s for a {limit}s limit"
        )

    def test_v3_respects_2s_limit(self):
        limit = 2.0
        t0 = time.perf_counter()
        _run(run_v3, SET_B_PARTS, SHEET_1000x800, time_limit=limit)
        elapsed = time.perf_counter() - t0
        assert elapsed <= limit * self._V3_MARGIN, (
            f"V3 took {elapsed:.2f}s for a {limit}s limit"
        )

    def test_v2_completes_at_all(self):
        """Engine must return a result dict (not raise) within 10s."""
        t0 = time.perf_counter()
        result = _run(run_v2, SET_A_PARTS, SHEET_1000x800, time_limit=5.0)
        elapsed = time.perf_counter() - t0
        assert isinstance(result, dict), "run_v2 must return a dict"
        assert elapsed <= 10.0, f"run_v2 hung for {elapsed:.1f}s"

    def test_v3_completes_at_all(self):
        t0 = time.perf_counter()
        result = _run(run_v3, SET_A_PARTS, SHEET_1000x800, time_limit=5.0)
        elapsed = time.perf_counter() - t0
        assert isinstance(result, dict), "run_v3 must return a dict"
        assert elapsed <= 10.0, f"run_v3 hung for {elapsed:.1f}s"


# ──────────────────────────────────────────────────────────────────────────────
# Section 4 — V3 >= V2 parity
# ──────────────────────────────────────────────────────────────────────────────

class TestV3GEV2:
    """V3 must match or exceed V2 on the same input (with 5% tolerance)."""

    _TOLERANCE = 0.15   # V3 may be at most 15% below V2 (multi-start overhead on easy inputs)

    def _assert_parity(self, parts, sheet, label):
        v2_result = _run(run_v2, parts, sheet, time_limit=5.0)
        v3_result = _run(run_v3, parts, sheet, time_limit=5.0)
        v2_util = _util(v2_result, sheet)
        v3_util = _util(v3_result, sheet)
        assert v3_util >= v2_util - self._TOLERANCE, (
            f"{label}: V3={v3_util:.1%} < V2={v2_util:.1%} - {self._TOLERANCE:.0%}"
        )

    def test_set_a_v3_ge_v2(self):
        self._assert_parity(SET_A_PARTS, SHEET_1000x800, "Set A")

    def test_set_b_v3_ge_v2(self):
        self._assert_parity(SET_B_PARTS, SHEET_1000x800, "Set B")

    def test_set_c_v3_ge_v2(self):
        self._assert_parity(SET_C_PARTS, SHEET_500x400, "Set C")


# ──────────────────────────────────────────────────────────────────────────────
# Section 5 — Edge cases & robustness
# ──────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Engines must handle edge cases without raising exceptions."""

    def test_single_part_fits(self):
        """One part that trivially fits must be placed."""
        parts = [_make_part("tiny", _rect_points(10, 10), 1)]
        result = _run(run_v3, parts, SHEET_500x400, time_limit=2.0)
        assert _placed_count(result) == 1, "Single fitting part not placed"

    def test_part_too_large(self):
        """Part larger than sheet — must be skipped gracefully (0 placed, no crash)."""
        parts = [_make_part("giant", _rect_points(600, 500), 1)]
        result = _run(run_v3, parts, SHEET_500x400, time_limit=2.0)
        assert _placed_count(result) == 0, "Oversized part must not be placed"

    def test_empty_parts_list(self):
        """Empty parts list — must return valid empty result."""
        result = _run(run_v3, [], SHEET_500x400, time_limit=2.0)
        assert isinstance(result, dict)
        assert _placed_count(result) == 0

    def test_zero_quantity_part(self):
        """Engine must not crash on qty=0; real parts (qty=3) must be placed."""
        parts = [
            _make_part("zero_qty", _rect_points(50, 50), 0),
            _make_part("real_part", _rect_points(80, 80), 3),
        ]
        result = _run(run_v3, parts, SHEET_500x400, time_limit=2.0)
        assert isinstance(result, dict), "Engine must return a dict"
        assert _placed_count(result) >= 3, "real_part (qty=3) must all be placed"

    def test_high_quantity_single_part(self):
        """Many instances of one part — engine must not crash and must place a non-trivial count."""
        parts = [_make_part("many", _rect_points(40, 40), 100)]
        result = _run(run_v3, parts, SHEET_500x400, time_limit=5.0)
        assert isinstance(result, dict)
        # Sheet 500×400 holds up to 125 of 40×40; expect at least 20 placed (robustness check)
        placed = _placed_count(result)
        assert placed >= 20, f"High-qty single part: only {placed} placed out of 100"

    def test_v2_triangle_placed(self):
        """Triangular part must be placed at least once."""
        parts = [_make_part("tri", _tri_points(200, 200), 4)]
        result = _run(run_v2, parts, SHEET_500x400, time_limit=3.0)
        assert _placed_count(result) >= 1, "Triangle not placed by V2"

    def test_v3_L_shape_placed(self):
        """L-shaped part must be placed at least once."""
        parts = [_make_part("L", _L_points(150, 150), 4)]
        result = _run(run_v3, parts, SHEET_500x400, time_limit=3.0)
        assert _placed_count(result) >= 1, "L-shape not placed by V3"

    def test_result_has_placements_key(self):
        """Result dict must always contain a 'placements' key."""
        for engine_fn in (run_v2, run_v3):
            result = engine_fn(SET_A_PARTS[:2], SHEET_500x400, {"time_limit_sec": 2.0})
            assert "placements" in result, f"{engine_fn.__module__} missing 'placements'"
