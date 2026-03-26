from __future__ import annotations

from dataclasses import dataclass

from shapely import affinity
from shapely.geometry import Polygon, box

EPSILON = 1e-6


@dataclass
class PartSpec:
    part_id: str
    polygon: Polygon
    quantity: int


@dataclass
class SheetSpec:
    sheet_id: str
    width: float
    height: float
    quantity: int


@dataclass
class Placement:
    part_id: str
    sheet_id: str
    instance: int
    rotation: int
    x: float
    y: float
    polygon: Polygon


def _bbox_dict(bounds: tuple[float, float, float, float]) -> dict[str, float]:
    min_x, min_y, max_x, max_y = bounds
    return {
        "min_x": float(min_x),
        "min_y": float(min_y),
        "max_x": float(max_x),
        "max_y": float(max_y),
        "width": float(max_x - min_x),
        "height": float(max_y - min_y),
    }


def _normalize_to_origin(polygon: Polygon) -> Polygon:
    min_x, min_y, _, _ = polygon.bounds
    return affinity.translate(polygon, xoff=-min_x, yoff=-min_y)


def _oriented_polygon(polygon: Polygon, rotation: int) -> Polygon:
    rotated = affinity.rotate(polygon, rotation, origin="centroid")
    return _normalize_to_origin(rotated)


def _sheet_instances(sheets: list[SheetSpec]) -> list[tuple[SheetSpec, int]]:
    instances: list[tuple[SheetSpec, int]] = []
    for sheet in sorted(sheets, key=lambda item: (item.sheet_id, item.width, item.height, item.quantity)):
        for index in range(sheet.quantity):
            instances.append((sheet, index + 1))
    return instances


def _fits(candidate: Polygon, placed: list[Polygon], sheet: SheetSpec, gap: float) -> bool:
    sheet_area = box(0, 0, sheet.width, sheet.height)
    if not candidate.within(sheet_area):
        return False
    candidate_gap = candidate.buffer(gap / 2.0, join_style="mitre")
    for item in placed:
        item_gap = item.buffer(gap / 2.0, join_style="mitre")
        if candidate_gap.intersection(item_gap).area > 1e-9:
            return False
    return True


def _validate_layout_metrics(layouts: list[dict], total_sheet_area: float, used_area: float, scrap_area: float, yield_value: float) -> dict:
    computed_used_area = 0.0
    computed_sheet_area = 0.0
    debug_sheets: list[dict] = []
    debug_placements: list[dict] = []
    warnings: list[str] = []
    global_bounds: tuple[float, float, float, float] | None = None
    max_sheet_extent = 0.0

    for layout in layouts:
        sheet_area = float(layout["width"]) * float(layout["height"])
        max_sheet_extent = max(max_sheet_extent, float(layout["width"]), float(layout["height"]))
        debug_sheets.append(
            {
                "sheet_id": layout["sheet_id"],
                "instance": layout["instance"],
                "width": float(layout["width"]),
                "height": float(layout["height"]),
                "area": sheet_area,
            }
        )
        placement_area = sum(float(placement.polygon.area) for placement in layout["placements"])
        if abs(layout["used_area"] - placement_area) > EPSILON:
            raise ValueError("Layout used area does not match placement geometry area")
        if abs(layout["scrap_area"] - max(sheet_area - placement_area, 0.0)) > EPSILON:
            raise ValueError("Layout scrap area does not match sheet minus used area")

        for index, placement in enumerate(layout["placements"]):
            if placement.polygon.is_empty or not placement.polygon.is_valid:
                raise ValueError("Placement polygon is invalid")
            if placement.polygon.area <= EPSILON:
                raise ValueError("Placement polygon area collapsed to zero")
            coords = list(placement.polygon.exterior.coords)
            if len(coords) < 4 or coords[0] != coords[-1]:
                raise ValueError("Placement polygon is not a closed valid ring")
            min_x, min_y, max_x, max_y = placement.polygon.bounds
            if min_x < -EPSILON or min_y < -EPSILON or max_x > float(layout["width"]) + EPSILON or max_y > float(layout["height"]) + EPSILON:
                raise ValueError("Placement polygon exceeds sheet bounds")
            global_bounds = (
                (min(global_bounds[0], min_x), min(global_bounds[1], min_y), max(global_bounds[2], max_x), max(global_bounds[3], max_y))
                if global_bounds
                else (min_x, min_y, max_x, max_y)
            )
            debug_placements.append(
                {
                    "placement_id": f"{placement.part_id}-{layout['sheet_id']}-{layout['instance']}-{index + 1}",
                    "part_id": placement.part_id,
                    "sheet_id": layout["sheet_id"],
                    "instance": layout["instance"],
                    "area": float(placement.polygon.area),
                    "bbox": _bbox_dict((min_x, min_y, max_x, max_y)),
                    "valid": bool(placement.polygon.is_valid),
                    "within_sheet": True,
                }
            )

        placements = layout["placements"]
        for left_index in range(len(placements)):
            for right_index in range(left_index + 1, len(placements)):
                overlap_area = float(placements[left_index].polygon.intersection(placements[right_index].polygon).area)
                if overlap_area > EPSILON:
                    raise ValueError("Placement polygons overlap")

        computed_used_area += placement_area
        computed_sheet_area += sheet_area

    if abs(used_area - computed_used_area) > EPSILON:
        raise ValueError("Aggregate used area does not match layout totals")
    if abs(total_sheet_area - computed_sheet_area) > EPSILON:
        raise ValueError("Aggregate sheet area does not match layout totals")
    if abs(scrap_area - max(total_sheet_area - used_area, 0.0)) > EPSILON:
        raise ValueError("Aggregate scrap area does not match sheet minus used area")
    expected_yield = (used_area / total_sheet_area) if total_sheet_area else 0.0
    if abs(yield_value - expected_yield) > EPSILON:
        raise ValueError("Yield does not match used area divided by total sheet area")
    if yield_value < -EPSILON or yield_value > 1.0 + EPSILON:
        raise ValueError("Yield is outside the valid [0, 1] range")
    if used_area < -EPSILON or scrap_area < -EPSILON:
        raise ValueError("Used or scrap area is negative")
    if used_area > total_sheet_area + EPSILON:
        raise ValueError("Used area exceeds available sheet area")

    placement_bounds = _bbox_dict(global_bounds) if global_bounds else None
    max_extent = max(placement_bounds["width"], placement_bounds["height"]) if placement_bounds else 0.0
    extent_ratio = (max_extent / max_sheet_extent) if max_sheet_extent else 0.0
    cluster_flagged = bool(debug_placements) and extent_ratio < 0.001
    if cluster_flagged:
        warnings.append("Placement extents are extremely small relative to the sheet; check geometry scale and units.")
        if yield_value > 0.001:
            raise ValueError("Placement distribution collapsed into an unrealistic cluster for the reported yield")

    if debug_placements and yield_value <= EPSILON and used_area > EPSILON:
        warnings.append("Non-zero used area produced a near-zero yield. This is mathematically valid but indicates a major scale mismatch.")

    return {
        "sheet": debug_sheets[0] if len(debug_sheets) == 1 else None,
        "sheets": debug_sheets,
        "placements": debug_placements,
        "total_used_area": float(used_area),
        "total_scrap_area": float(scrap_area),
        "scale_info": {
            "placement_bounds": placement_bounds,
            "max_extent": float(max_extent),
            "sheet_max_extent": float(max_sheet_extent),
            "extent_ratio": float(extent_ratio),
            "cluster_flagged": cluster_flagged,
        },
        "warnings": warnings,
    }


def nest(parts: list[PartSpec], sheets: list[SheetSpec], params: dict) -> dict:
    gap = float(params.get("gap", 0.0))
    rotations = [rotation for rotation in params.get("rotation", [0, 180]) if rotation in {0, 180}] or [0]
    debug_enabled = bool(params.get("debug", False))

    demand: list[tuple[str, Polygon]] = []
    for part in parts:
        for _ in range(part.quantity):
            demand.append((part.part_id, part.polygon))

    # Greedy placement is more stable when larger parts are handled first.
    demand.sort(key=lambda item: (-round(item[1].area, 6), item[0], item[1].bounds))

    layout_map: dict[tuple[str, int], list[Placement]] = {}
    geometry_map: dict[tuple[str, int], list[Polygon]] = {}
    unplaced: list[str] = []

    for part_id, polygon in demand:
        placed = False
        for sheet, instance in _sheet_instances(sheets):
            placed_polygons = geometry_map.setdefault((sheet.sheet_id, instance), [])
            x_candidates = sorted({0.0, *[round(item.bounds[2] + gap, 6) for item in placed_polygons]})
            y_candidates = sorted({0.0, *[round(item.bounds[3] + gap, 6) for item in placed_polygons]})

            for rotation in rotations:
                oriented = _oriented_polygon(polygon, rotation)
                width = oriented.bounds[2]
                height = oriented.bounds[3]
                for y in y_candidates:
                    for x in x_candidates:
                        if x + width > sheet.width or y + height > sheet.height:
                            continue
                        candidate = affinity.translate(oriented, xoff=x, yoff=y)
                        if not _fits(candidate, placed_polygons, sheet, gap):
                            continue
                        placement = Placement(
                            part_id=part_id,
                            sheet_id=sheet.sheet_id,
                            instance=instance,
                            rotation=rotation,
                            x=x,
                            y=y,
                            polygon=candidate,
                        )
                        layout_map.setdefault((sheet.sheet_id, instance), []).append(placement)
                        placed_polygons.append(candidate)
                        placed = True
                        break
                    if placed:
                        break
                if placed:
                    break
            if placed:
                break
        if not placed:
            unplaced.append(part_id)

    layouts = []
    total_sheet_area = 0.0
    used_area = 0.0
    for sheet, instance in _sheet_instances(sheets):
        placements = layout_map.get((sheet.sheet_id, instance), [])
        if not placements:
            continue
        sheet_area = sheet.width * sheet.height
        consumed = sum(item.polygon.area for item in placements)
        total_sheet_area += sheet_area
        used_area += consumed
        layouts.append(
            {
                "sheet_id": sheet.sheet_id,
                "instance": instance,
                "width": sheet.width,
                "height": sheet.height,
                "placements": placements,
                "used_area": consumed,
                "scrap_area": max(sheet_area - consumed, 0.0),
            }
        )

    scrap_area = max(total_sheet_area - used_area, 0.0)
    yield_value = (used_area / total_sheet_area) if total_sheet_area else 0.0
    parts_placed = sum(len(layout["placements"]) for layout in layouts)
    layouts_used = len(layouts)
    scrap_ratio = (scrap_area / total_sheet_area) if total_sheet_area else 0.0
    layouts.sort(key=lambda item: (item["sheet_id"], item["instance"]))
    for layout in layouts:
        layout["placements"].sort(key=lambda item: (item.y, item.x, item.part_id, item.instance))
    debug_summary = _validate_layout_metrics(layouts, total_sheet_area, used_area, scrap_area, yield_value)

    result = {
        "yield": yield_value,
        "yield_ratio": yield_value,
        "scrap_ratio": scrap_ratio,
        "scrap_area": scrap_area,
        "used_area": used_area,
        "total_sheet_area": total_sheet_area,
        "parts_placed": parts_placed,
        "layouts_used": layouts_used,
        "layouts": layouts,
        "unplaced_parts": unplaced,
    }
    if debug_enabled:
        result["debug"] = debug_summary
    return result
