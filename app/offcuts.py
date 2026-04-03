from __future__ import annotations

from collections.abc import Iterable

from shapely.ops import unary_union


EPSILON = 1e-6


def _leftover_summary_from_offcut(offcut: dict[str, object]) -> dict[str, object]:
    bounds = offcut.get("bounds") if isinstance(offcut.get("bounds"), dict) else {}
    return {
        "sheet_id": str(offcut.get("sheet_id") or "sheet-1"),
        "instance": int(offcut.get("instance") or 1),
        "width": float(bounds.get("width") or 0.0),
        "height": float(bounds.get("height") or 0.0),
        "area": float(offcut.get("area") or 0.0),
        "approximate": offcut.get("approximation") is not False,
        "source": str(offcut.get("source") or "unknown"),
    }


def _bounds_payload(min_x: float, min_y: float, max_x: float, max_y: float) -> dict[str, float]:
    return {
        "min_x": float(min_x),
        "min_y": float(min_y),
        "max_x": float(max_x),
        "max_y": float(max_y),
        "width": float(max(max_x - min_x, 0.0)),
        "height": float(max(max_y - min_y, 0.0)),
    }


def _build_rectangular_offcut(
    *,
    sheet_id: str,
    instance: int,
    x: float,
    y: float,
    width: float,
    height: float,
    source: str,
) -> dict[str, object] | None:
    area = float(max(width, 0.0) * max(height, 0.0))
    if area <= EPSILON:
        return None
    return {
        "sheet_id": sheet_id,
        "instance": instance,
        "area": area,
        "approx_shape": "rectangle",
        "bounds": _bounds_payload(x, y, x + width, y + height),
        "reusable": True,
        "approximation": True,
        "source": source,
    }


def summarize_sheet_offcuts(
    *,
    sheet_id: str,
    instance: int,
    sheet_width: float,
    sheet_height: float,
    used_area: float,
    scrap_area: float,
    placement_polygons: Iterable[object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    polygons = [polygon for polygon in placement_polygons if polygon is not None and not polygon.is_empty]
    if not polygons:
        full_sheet = _build_rectangular_offcut(
            sheet_id=sheet_id,
            instance=instance,
            x=0.0,
            y=0.0,
            width=sheet_width,
            height=sheet_height,
            source="empty_sheet",
        )
        offcuts = [full_sheet] if full_sheet else []
        return offcuts, {
            "sheet_id": sheet_id,
            "instance": instance,
            "sheet_area": float(sheet_width * sheet_height),
            "used_area": float(used_area),
            "scrap_area": float(scrap_area),
            "reusable_leftover_area": float(scrap_area),
            "estimated_scrap_area": 0.0,
            "reusable_piece_count": len(offcuts),
            "approximation": True,
            "approximation_method": "full_sheet_rectangle",
            "message": "No placements were present, so the whole sheet is treated as one reusable rectangular leftover.",
        }

    union = unary_union(polygons)
    min_x, min_y, max_x, max_y = union.bounds

    candidates = [
        _build_rectangular_offcut(
            sheet_id=sheet_id,
            instance=instance,
            x=0.0,
            y=0.0,
            width=min_x,
            height=sheet_height,
            source="left_strip",
        ),
        _build_rectangular_offcut(
            sheet_id=sheet_id,
            instance=instance,
            x=max_x,
            y=0.0,
            width=sheet_width - max_x,
            height=sheet_height,
            source="right_strip",
        ),
        _build_rectangular_offcut(
            sheet_id=sheet_id,
            instance=instance,
            x=min_x,
            y=0.0,
            width=max_x - min_x,
            height=min_y,
            source="bottom_strip",
        ),
        _build_rectangular_offcut(
            sheet_id=sheet_id,
            instance=instance,
            x=min_x,
            y=max_y,
            width=max_x - min_x,
            height=sheet_height - max_y,
            source="top_strip",
        ),
    ]
    offcuts = [candidate for candidate in candidates if candidate is not None]
    reusable_area = float(sum(float(item["area"]) for item in offcuts))
    estimated_scrap_area = float(max(scrap_area - reusable_area, 0.0))

    return offcuts, {
        "sheet_id": sheet_id,
        "instance": instance,
        "sheet_area": float(sheet_width * sheet_height),
        "used_area": float(used_area),
        "scrap_area": float(scrap_area),
        "reusable_leftover_area": reusable_area,
        "estimated_scrap_area": estimated_scrap_area,
        "reusable_piece_count": len(offcuts),
        "approximation": True,
        "approximation_method": "bounding_box_strips",
        "message": "Reusable leftovers are approximated as rectangular strips outside the placed-parts bounding box. Internal gaps remain estimated scrap until polygonal recovery is added.",
    }


def summarize_job_offcuts(layouts: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    offcuts: list[dict[str, object]] = []
    sheet_summaries: list[dict[str, object]] = []

    for layout in layouts:
        layout_offcuts, summary = summarize_sheet_offcuts(
            sheet_id=str(layout["sheet_id"]),
            instance=int(layout["instance"]),
            sheet_width=float(layout["width"]),
            sheet_height=float(layout["height"]),
            used_area=float(layout["used_area"]),
            scrap_area=float(layout["scrap_area"]),
            placement_polygons=[placement.polygon for placement in layout["placements"]],
        )
        offcuts.extend(layout_offcuts)
        sheet_summaries.append(summary)

    total_leftover_area = float(sum(float(item["scrap_area"]) for item in sheet_summaries))
    reusable_leftover_area = float(sum(float(item["reusable_leftover_area"]) for item in sheet_summaries))
    estimated_scrap_area = float(sum(float(item["estimated_scrap_area"]) for item in sheet_summaries))
    leftover_summaries = [_leftover_summary_from_offcut(item) for item in offcuts]

    return offcuts, {
        "total_leftover_area": total_leftover_area,
        "reusable_leftover_area": reusable_leftover_area,
        "reusable_area_estimate": reusable_leftover_area,
        "estimated_scrap_area": estimated_scrap_area,
        "reusable_piece_count": len(offcuts),
        "approximation": bool(sheet_summaries),
        "approximation_method": "bounding_box_strips" if sheet_summaries else "not_available",
        "message": (
            "Reusable leftovers are simplified approximations. Total scrap is exact, but reusable shapes are limited to rectangular strip estimates for now."
            if sheet_summaries
            else "No used layouts were available, so leftover analysis could not be computed."
        ),
        "leftover_summaries": leftover_summaries,
        "sheets": sheet_summaries,
    }
