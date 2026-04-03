from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 0:
            return number
    return None


def _round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _round_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


def build_economic_metrics(material: dict[str, Any] | None, result: dict[str, Any] | None) -> dict[str, object]:
    if not isinstance(material, dict):
        return {
            "status": "placeholder",
            "material_cost": None,
            "used_material_cost": None,
            "waste_cost": None,
            "savings_percent": None,
            "currency": None,
            "cost_basis": None,
            "material_cost_estimated": False,
            "used_material_cost_estimated": False,
            "waste_cost_estimated": False,
            "savings_percent_estimated": False,
            "message": "Economics unavailable. Add a sheet cost on Screen 2 to estimate material value.",
        }

    cost_per_sheet = _to_float(material.get("cost_per_sheet"))
    currency = str(material.get("currency")).strip() if material.get("currency") is not None else None
    currency = currency or None
    if cost_per_sheet is None:
        return {
            "status": "placeholder",
            "material_cost": None,
            "used_material_cost": None,
            "waste_cost": None,
            "savings_percent": None,
            "currency": currency,
            "cost_basis": None,
            "material_cost_estimated": False,
            "used_material_cost_estimated": False,
            "waste_cost_estimated": False,
            "savings_percent_estimated": False,
            "message": "Economics unavailable. Add a per-sheet material cost to estimate used, waste, and recoverable value.",
        }

    result_data = result if isinstance(result, dict) else {}
    total_sheet_area = _to_float(result_data.get("total_sheet_area"))
    sheet_width = _to_float(material.get("sheet_width"))
    sheet_height = _to_float(material.get("sheet_height"))
    sheet_area = (sheet_width * sheet_height) if sheet_width and sheet_height else None
    if total_sheet_area is None or sheet_area is None:
        return {
            "status": "placeholder",
            "material_cost": None,
            "used_material_cost": None,
            "waste_cost": None,
            "savings_percent": None,
            "currency": currency,
            "cost_basis": "per_sheet",
            "material_cost_estimated": False,
            "used_material_cost_estimated": False,
            "waste_cost_estimated": False,
            "savings_percent_estimated": False,
            "message": "Economics unavailable because sheet dimensions or result area are missing.",
        }

    layout_count = _to_float(result_data.get("layouts_used"))
    sheet_count = layout_count if layout_count is not None else max(total_sheet_area / sheet_area, 0.0)
    material_cost = _round_money(sheet_count * cost_per_sheet)

    used_area = max(float(result_data.get("used_area") or 0.0), 0.0)
    scrap_area = max(float(result_data.get("scrap_area") or 0.0), 0.0)
    used_ratio = min(max(used_area / total_sheet_area, 0.0), 1.0) if total_sheet_area > 0 else 0.0
    scrap_ratio = min(max(scrap_area / total_sheet_area, 0.0), 1.0) if total_sheet_area > 0 else 0.0

    offcut_summary = result_data.get("offcut_summary") if isinstance(result_data.get("offcut_summary"), dict) else {}
    reusable_leftover_area = max(float(offcut_summary.get("reusable_leftover_area") or 0.0), 0.0)
    savings_percent = (
        _round_percent((reusable_leftover_area / total_sheet_area) * 100.0) if total_sheet_area > 0 and reusable_leftover_area > 0 else None
    )

    return {
        "status": "available",
        "material_cost": material_cost,
        "used_material_cost": _round_money(material_cost * used_ratio if material_cost is not None else None),
        "waste_cost": _round_money(material_cost * scrap_ratio if material_cost is not None else None),
        "savings_percent": savings_percent,
        "currency": currency,
        "cost_basis": "per_sheet",
        "material_cost_estimated": False,
        "used_material_cost_estimated": True,
        "waste_cost_estimated": True,
        "savings_percent_estimated": savings_percent is not None,
        "message": (
            "Total sheet spend uses the configured per-sheet cost. Used, waste, and recoverable savings values are area-based estimates."
        ),
    }
