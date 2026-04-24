"""
Nestora Benchmark Suite — измерение утилизации до/после каждого изменения.
Запуск: python tests/benchmark_suite.py
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

# ──────────────────────────────────────────────────────────────────────────────
# Тестовые листы
# ──────────────────────────────────────────────────────────────────────────────

SHEET_1000x800  = {"sheet_id": "s1", "width": 1000, "height": 800,  "quantity": 1}
SHEET_1000x2000 = {"sheet_id": "s1", "width": 1000, "height": 2000, "quantity": 1}

# ──────────────────────────────────────────────────────────────────────────────
# Set A: 50 прямоугольников — должны давать 85%+ в мировых системах
# ──────────────────────────────────────────────────────────────────────────────

SET_A_RECTS = [
    {"w": 200, "h": 150, "qty": 4},
    {"w": 300, "h": 100, "qty": 6},
    {"w": 150, "h": 150, "qty": 8},
    {"w": 120, "h":  80, "qty": 10},
    {"w": 250, "h": 200, "qty": 6},
    {"w":  80, "h":  60, "qty": 16},
]  # итого 50 деталей

# ──────────────────────────────────────────────────────────────────────────────
# Set B: 32 смешанных формы (текущий провальный тест)
# ──────────────────────────────────────────────────────────────────────────────

SET_B_MIXED = [
    {"type": "rect",  "w": 150, "h": 100, "qty": 4},
    {"type": "rect",  "w": 200, "h":  80, "qty": 3},
    {"type": "rect",  "w": 100, "h": 120, "qty": 5},
    {"type": "rect",  "w":  80, "h":  80, "qty": 4},
    {"type": "rect",  "w": 300, "h":  60, "qty": 2},
    {"type": "tri",   "w": 150, "h": 100, "qty": 3},
    {"type": "tri",   "w": 100, "h":  80, "qty": 4},
    {"type": "tri",   "w": 200, "h": 120, "qty": 2},
    {"type": "L",     "w": 120, "h": 150, "qty": 3},
    {"type": "L",     "w": 100, "h": 200, "qty": 2},
]  # итого 32 детали

# ──────────────────────────────────────────────────────────────────────────────
# Конвертеры в API-формат
# ──────────────────────────────────────────────────────────────────────────────

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


def _hex_points(r: float) -> list[dict]:
    pts = [
        {"x": round(r * math.cos(2 * math.pi * k / 6 + math.pi / 6), 6),
         "y": round(r * math.sin(2 * math.pi * k / 6 + math.pi / 6), 6)}
        for k in range(6)
    ]
    pts.append(pts[0])
    # shift to non-negative
    min_x = min(p["x"] for p in pts)
    min_y = min(p["y"] for p in pts)
    return [{"x": p["x"] - min_x, "y": p["y"] - min_y} for p in pts]


def rects_to_parts(specs: list[dict]) -> list[dict]:
    """Convert [{w, h, qty}] → API part list."""
    parts = []
    for i, s in enumerate(specs):
        w, h, qty = s["w"], s["h"], s["qty"]
        parts.append({
            "part_id": f"r{i}_{w}x{h}",
            "polygon": {"points": _rect_points(w, h)},
            "quantity": qty,
        })
    return parts


def mixed_to_parts(specs: list[dict]) -> list[dict]:
    """Convert mixed [{type, w, h, qty}] → API part list."""
    parts = []
    for i, s in enumerate(specs):
        t = s.get("type", "rect")
        w, h, qty = s["w"], s["h"], s["qty"]
        if t == "rect":
            pts = _rect_points(w, h)
        elif t == "tri":
            pts = _tri_points(w, h)
        elif t == "L":
            pts = _L_points(w, h)
        else:
            pts = _rect_points(w, h)
        parts.append({
            "part_id": f"{t}{i}_{w}x{h}",
            "polygon": {"points": pts},
            "quantity": qty,
        })
    return parts


# ──────────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────────

def _part_area(pts: list[dict]) -> float:
    area = 0.0
    for j in range(len(pts) - 1):
        area += pts[j]["x"] * pts[j + 1]["y"] - pts[j + 1]["x"] * pts[j]["y"]
    return abs(area) / 2.0


def theoretical_yield(parts: list[dict], sheet: dict) -> float:
    total = sum(_part_area(p["polygon"]["points"]) * p["quantity"] for p in parts)
    return total / (sheet["width"] * sheet["height"])


def run_benchmark(
    engine_fn,
    parts: list[dict],
    sheet: dict,
    label: str,
    time_limit: float = 5.0,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        result = engine_fn(parts, sheet, {"time_limit_sec": time_limit})
    except Exception as exc:
        print(f"  {'ERROR':30s} {label}: {exc}")
        return {"util": 0.0, "placed": 0, "total": 0, "time_s": 0.0, "error": str(exc)}
    elapsed = time.perf_counter() - t0

    metrics = result.get("metrics", {})
    util = metrics.get("yield_ratio") or metrics.get("yield") or 0.0
    placed = metrics.get("placed_parts") or metrics.get("placed_count") or len(result.get("placements", []))
    total = sum(p["quantity"] for p in parts)
    v3_info = result.get("v3_info", {})

    extras = ""
    if v3_info:
        ms = v3_info.get("multi_start", {})
        ls = v3_info.get("local_search", {})
        extras = f"  restarts={ms.get('restarts','?')} swaps={ls.get('swaps','?')}"

    print(
        f"  {label:35s}  util={util:6.1%}  placed={placed:3d}/{total:<3d}"
        f"  t={elapsed:5.1f}s{extras}"
    )
    return {"util": util, "placed": placed, "total": total, "time_s": elapsed}


# ──────────────────────────────────────────────────────────────────────────────
# Главная функция
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    from app.nesting_v2 import run_nesting as run_v2
    from app.nesting_v3 import run_nesting as run_v3

    print("=" * 70)
    print("NESTORA BENCHMARK SUITE")
    print("=" * 70)

    # ── Set A: rectangles ─────────────────────────────────────────────────
    parts_a = rects_to_parts(SET_A_RECTS)
    ty_a = theoretical_yield(parts_a, SHEET_1000x800)
    total_a = sum(p["quantity"] for p in parts_a)
    print(f"\n[SET A] {len(parts_a)} rect types, {total_a} instances -- sheet 1000x800"
          f"  (theoretical max {ty_a:.1%})")

    run_benchmark(run_v2, parts_a, SHEET_1000x800, "V2")
    run_benchmark(run_v3, parts_a, SHEET_1000x800, "V3")

    # BASELINE (update after first run):
    # V2 baseline: util= 50.0%
    # V3 baseline: util= 50.0%

    # ── Set B: mixed shapes ───────────────────────────────────────────────
    parts_b = mixed_to_parts(SET_B_MIXED)
    ty_b = theoretical_yield(parts_b, SHEET_1000x800)
    total_b = sum(p["quantity"] for p in parts_b)
    print(f"\n[SET B] {len(parts_b)} mixed types, {total_b} instances -- sheet 1000x800"
          f"  (theoretical max {ty_b:.1%})")

    run_benchmark(run_v2, parts_b, SHEET_1000x800, "V2")
    run_benchmark(run_v3, parts_b, SHEET_1000x800, "V3")

    # BASELINE:
    # V2 baseline: util= 19.9%
    # V3 baseline: util= 22.1%

    # ── Set C: dense identical rectangles (ideal case) ────────────────────
    parts_c = [{"part_id": "r", "polygon": {"points": _rect_points(100, 40)}, "quantity": 50}]
    sheet_c = {"sheet_id": "s1", "width": 500, "height": 400, "quantity": 1}
    ty_c = theoretical_yield(parts_c, sheet_c)
    print(f"\n[SET C] 50x 100x40 -- sheet 500x400  (theoretical max {ty_c:.1%})")

    run_benchmark(run_v2, parts_c, sheet_c, "V2")
    run_benchmark(run_v3, parts_c, sheet_c, "V3")

    # BASELINE:
    # V2 baseline: util= 50.0%
    # V3 baseline: util= 50.0%

    print("\n" + "=" * 70)
    print("Targets after Step 1:")
    print("  Set A V3  >= 85%")
    print("  Set B V3  >= 40%")
    print("  Set C V3  >= 90%")
    print("=" * 70)


if __name__ == "__main__":
    main()
