from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shapely import affinity
from shapely.geometry import Polygon, box

EPSILON = 1e-6
NestingMode = Literal["fill_sheet", "batch_quantity"]


@dataclass
class PartSpec:
    part_id: str
    polygon: Polygon
    quantity: int
    filename: str | None = None
    enabled: bool = True
    fill_only: bool = False


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


def _candidate_parts(parts: list[PartSpec], mode: NestingMode, remaining: dict[str, int]) -> list[PartSpec]:
    candidates = [part for part in parts if part.enabled and (mode == "fill_sheet" or remaining[part.part_id] > 0)]
    solo_parts = [part for part in candidates if part.fill_only]
    if mode == "fill_sheet" and solo_parts:
        candidates = solo_parts
    return sorted(candidates, key=lambda item: (-round(item.polygon.area, 6), item.filename or item.part_id, item.part_id))


def _find_placement(
    part: PartSpec,
    sheet: SheetSpec,
    instance: int,
    placed_polygons: list[Polygon],
    placed_count: int,
    rotations: list[int],
    gap: float,
) -> Placement | None:
    for rotation in rotations:
        oriented = _oriented_polygon(part.polygon, rotation)
        part_width = oriented.bounds[2]
        part_height = oriented.bounds[3]
        
        # Build candidates from edge positions
        x_edge_candidates = sorted({0.0, *[round(item.bounds[2] + gap, 6) for item in placed_polygons]})
        y_edge_candidates = sorted({0.0, *[round(item.bounds[3] + gap, 6) for item in placed_polygons]})
        
        # For fill_sheet mode, add grid sampling to explore the sheet more thoroughly
        # This helps find empty spaces that edge-based candidates don't cover
        x_candidates_list = list(x_edge_candidates)
        y_candidates_list = list(y_edge_candidates)
        
        # Add more granular grid points if sheet has significant empty space
        if not placed_polygons or (sheet.width * sheet.height > sum(p.area for p in placed_polygons) * 3):
            grid_step_x = max(part_width * 0.75, 0.5)
            grid_step_y = max(part_height * 0.75, 0.5)
            
            x_pos = grid_step_x
            while x_pos < sheet.width:
                x_candidates_list.append(round(x_pos, 6))
                x_pos += grid_step_x
            
            y_pos = grid_step_y
            while y_pos < sheet.height:
                y_candidates_list.append(round(y_pos, 6))
                y_pos += grid_step_y
        
        x_candidates = sorted(set(x_candidates_list))
        y_candidates = sorted(set(y_candidates_list))
        
        for y in y_candidates:
            if y + part_height > sheet.height + EPSILON:
                continue
            for x in x_candidates:
                if x + part_width > sheet.width + EPSILON:
                    continue
                candidate = affinity.translate(oriented, xoff=x, yoff=y)
                if not _fits(candidate, placed_polygons, sheet, gap):
                    continue
                return Placement(
                    part_id=part.part_id,
                    sheet_id=sheet.sheet_id,
                    instance=placed_count + 1,
                    rotation=rotation,
                    x=x,
                    y=y,
                    polygon=candidate,
                )
    return None


def nest(parts: list[PartSpec], sheets: list[SheetSpec], params: dict) -> dict:
    mode = params.get("mode", "batch_quantity")
    if mode not in {"fill_sheet", "batch_quantity"}:
        raise ValueError("Unsupported nesting mode")

    gap = float(params.get("gap", 0.0))
    rotations = [rotation for rotation in params.get("rotation", [0, 180]) if rotation in {0, 180}] or [0]
    debug_enabled = bool(params.get("debug", False))
    source_units = params.get("source_units")
    source_max_extent = float(params["source_max_extent"]) if params.get("source_max_extent") else None

    active_parts = [part for part in parts if part.enabled]
    if not active_parts:
        raise ValueError("At least one enabled part is required")

    remaining: dict[str, int] = {part.part_id: part.quantity for part in active_parts}
    part_lookup = {part.part_id: part for part in active_parts}
    placed_counts = {part.part_id: 0 for part in active_parts}
    area_contribution = {part.part_id: 0.0 for part in active_parts}

    layout_map: dict[tuple[str, int], list[Placement]] = {}
    geometry_map: dict[tuple[str, int], list[Polygon]] = {}

    stop_filling = False
    for sheet, instance in _sheet_instances(sheets):
        placed_polygons = geometry_map.setdefault((sheet.sheet_id, instance), [])
        while not stop_filling:
            placed_any = False
            for part in _candidate_parts(active_parts, mode, remaining):
                placement = _find_placement(
                    part,
                    sheet,
                    instance,
                    placed_polygons,
                    placed_counts[part.part_id],
                    rotations,
                    gap,
                )
                if not placement:
                    continue
                layout_map.setdefault((sheet.sheet_id, instance), []).append(placement)
                placed_polygons.append(placement.polygon)
                placed_counts[part.part_id] += 1
                area_contribution[part.part_id] += float(placement.polygon.area)
                if mode == "batch_quantity":
                    remaining[part.part_id] = max(remaining[part.part_id] - 1, 0)
                    if all(value == 0 for value in remaining.values()):
                        stop_filling = True
                placed_any = True
                break
            if not placed_any:
                break
        if stop_filling:
            break

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
    parts_placed = sum(placed_counts.values())
    layouts_used = len(layouts)
    scrap_ratio = (scrap_area / total_sheet_area) if total_sheet_area else 0.0
    layouts.sort(key=lambda item: (item["sheet_id"], item["instance"]))
    for layout in layouts:
        layout["placements"].sort(key=lambda item: (item.y, item.x, item.part_id, item.instance))
    debug_summary = _validate_layout_metrics(layouts, total_sheet_area, used_area, scrap_area, yield_value)

    part_summaries = [
        {
            "part_id": part.part_id,
            "filename": part.filename,
            "requested_quantity": part.quantity if mode == "batch_quantity" else None,
            "placed_quantity": placed_counts[part.part_id],
            "remaining_quantity": max(remaining[part.part_id], 0) if mode == "batch_quantity" else None,
            "enabled": part.enabled,
            "area_contribution": area_contribution[part.part_id],
        }
        for part in _candidate_parts(active_parts, mode, remaining) + [part for part in active_parts if part.part_id not in {item.part_id for item in _candidate_parts(active_parts, mode, remaining)}]
    ]
    part_summaries.sort(key=lambda item: (item["filename"] or item["part_id"], item["part_id"]))

    unplaced = sorted(
        [part_id for part_id, count in remaining.items() if count > 0]
    ) if mode == "batch_quantity" else []

    warnings: list[str] = []
    max_sheet_extent = max((max(sheet.width, sheet.height) for sheet in sheets), default=0.0)
    if source_units in {"Inches", "Feet", "Yards", "Unitless", None} and source_max_extent and max_sheet_extent:
        scale_ratio = max_sheet_extent / source_max_extent
        if scale_ratio >= 25:
            unit_label = source_units or "unknown"
            warnings.append(
                f"Possible scale mismatch: source geometry max extent is {source_max_extent:.3f} {unit_label}, while sheet max extent is {max_sheet_extent:.3f}. Verify matching units before trusting yield and scrap."
            )
    if mode == "fill_sheet" and parts_placed <= 1:
        if len(active_parts) >= 1 and any(p.polygon.area * 4 <= sheet.width * sheet.height for p in active_parts for sheet in sheets):
            warnings.append("Fill Sheet mode only placed one part. Check part size, sheet size, and valid geometry. This may indicate a scale mismatch or unusually large parts.")

    result = {
        "mode": mode,
        "yield": yield_value,
        "yield_ratio": yield_value,
        "scrap_ratio": scrap_ratio,
        "scrap_area": scrap_area,
        "used_area": used_area,
        "total_sheet_area": total_sheet_area,
        "parts_placed": parts_placed,
        "layouts_used": layouts_used,
        "layouts": layouts,
        "part_summaries": part_summaries,
        "unplaced_parts": unplaced,
        "warnings": warnings,
    }
    if debug_enabled:
        result["debug"] = debug_summary
    return result
