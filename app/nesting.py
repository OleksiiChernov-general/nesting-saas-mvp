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


def _is_nestable_part(part: PartSpec) -> bool:
    polygon = part.polygon
    return bool(
        polygon
        and not polygon.is_empty
        and polygon.is_valid
        and polygon.area > EPSILON
        and getattr(polygon, "exterior", None) is not None
    )


def _candidate_axis_positions(
    placed_polygons: list[Polygon],
    limit: float,
    size: float,
    gap: float,
    axis: Literal["x", "y"],
) -> list[float]:
    if size > limit + EPSILON:
        return []

    max_anchor = max(limit - size, 0.0)
    positions = {0.0, round(max_anchor, 6)}

    for polygon in placed_polygons:
        min_x, min_y, max_x, max_y = polygon.bounds
        axis_min, axis_max = (min_x, max_x) if axis == "x" else (min_y, max_y)
        raw_positions = {
            axis_min,
            axis_max + gap,
            axis_min - size - gap,
            axis_max - size,
            axis_min - size,
        }
        for raw in raw_positions:
            if raw < -EPSILON or raw > max_anchor + EPSILON:
                continue
            positions.add(round(min(max(raw, 0.0), max_anchor), 6))

    grid_step = max(size * 0.5, 0.5)
    cursor = 0.0
    while cursor <= max_anchor + EPSILON:
        positions.add(round(min(cursor, max_anchor), 6))
        cursor += grid_step

    return sorted(positions)


def _contact_score(candidate: Polygon, placed_polygons: list[Polygon], sheet: SheetSpec, gap: float) -> int:
    min_x, min_y, max_x, max_y = candidate.bounds
    score = 0
    if min_x <= EPSILON:
        score += 1
    if min_y <= EPSILON:
        score += 1
    if abs(sheet.width - max_x) <= EPSILON:
        score += 1
    if abs(sheet.height - max_y) <= EPSILON:
        score += 1

    proximity_limit = max(gap + EPSILON, EPSILON)
    for polygon in placed_polygons:
        if candidate.distance(polygon) <= proximity_limit:
            score += 1
    return score


def _placement_score(
    *,
    part: PartSpec,
    candidate: Polygon,
    parts: list[PartSpec],
    placed_polygons: list[Polygon],
    sheet: SheetSpec,
    gap: float,
    rotations: list[int],
    mode: NestingMode,
    remaining: dict[str, int],
) -> tuple[float, float, int, float, float, float]:
    min_x, min_y, max_x, max_y = candidate.bounds
    contact_score = _contact_score(candidate, placed_polygons, sheet, gap)
    backlog_area = float(max(remaining.get(part.part_id, 0), 1)) * float(part.polygon.area)
    primary_score = backlog_area if mode == "batch_quantity" else float(part.polygon.area)
    future_remaining = dict(remaining)
    if mode == "batch_quantity":
        future_remaining[part.part_id] = max(future_remaining.get(part.part_id, 0) - 1, 0)
    future_score = _future_productive_area(
        parts=parts,
        sheet=sheet,
        placed_polygons=placed_polygons + [candidate],
        rotations=rotations,
        gap=gap,
        mode=mode,
        remaining=future_remaining,
    )
    return (
        primary_score + (future_score * 0.35),
        future_score,
        contact_score,
        -float(max_y),
        -float(max_x),
        -(float(min_y) + float(min_x)),
    )


def _future_productive_area(
    *,
    parts: list[PartSpec],
    sheet: SheetSpec,
    placed_polygons: list[Polygon],
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    remaining: dict[str, int],
) -> float:
    best_area = 0.0
    for part in _candidate_parts(parts, mode, remaining):
        part_area = float(part.polygon.area)
        for rotation in rotations:
            oriented = _oriented_polygon(part.polygon, rotation)
            part_width = oriented.bounds[2]
            part_height = oriented.bounds[3]
            x_candidates = _candidate_axis_positions(placed_polygons, sheet.width, part_width, gap, "x")
            y_candidates = _candidate_axis_positions(placed_polygons, sheet.height, part_height, gap, "y")

            fits = False
            for y in y_candidates:
                if y + part_height > sheet.height + EPSILON:
                    continue
                for x in x_candidates:
                    if x + part_width > sheet.width + EPSILON:
                        continue
                    candidate = affinity.translate(oriented, xoff=x, yoff=y)
                    if _fits(candidate, placed_polygons, sheet, gap):
                        fits = True
                        break
                if fits:
                    break
            if fits:
                best_area = max(best_area, part_area)
                break
    return best_area


def _best_placement_for_part(
    *,
    parts: list[PartSpec],
    part: PartSpec,
    sheet: SheetSpec,
    placed_polygons: list[Polygon],
    placed_count: int,
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    remaining: dict[str, int],
) -> tuple[Placement, tuple[float, float, int, float, float, float]] | None:
    best_match: tuple[Placement, tuple[float, float, int, float, float, float]] | None = None

    for rotation in rotations:
        oriented = _oriented_polygon(part.polygon, rotation)
        part_width = oriented.bounds[2]
        part_height = oriented.bounds[3]
        x_candidates = _candidate_axis_positions(placed_polygons, sheet.width, part_width, gap, "x")
        y_candidates = _candidate_axis_positions(placed_polygons, sheet.height, part_height, gap, "y")

        for y in y_candidates:
            if y + part_height > sheet.height + EPSILON:
                continue
            for x in x_candidates:
                if x + part_width > sheet.width + EPSILON:
                    continue
                candidate = affinity.translate(oriented, xoff=x, yoff=y)
                if not _fits(candidate, placed_polygons, sheet, gap):
                    continue

                placement = Placement(
                    part_id=part.part_id,
                    sheet_id=sheet.sheet_id,
                    instance=placed_count + 1,
                    rotation=rotation,
                    x=x,
                    y=y,
                    polygon=candidate,
                )
                score = _placement_score(
                    part=part,
                    candidate=candidate,
                    parts=parts,
                    placed_polygons=placed_polygons,
                    sheet=sheet,
                    gap=gap,
                    rotations=rotations,
                    mode=mode,
                    remaining=remaining,
                )
                if best_match is None or score > best_match[1]:
                    best_match = (placement, score)

    return best_match


def _select_next_placement(
    *,
    parts: list[PartSpec],
    sheet: SheetSpec,
    placed_polygons: list[Polygon],
    placed_counts: dict[str, int],
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    remaining: dict[str, int],
) -> Placement | None:
    best_choice: tuple[Placement, tuple[float, float, int, float, float, float], tuple[float, float, str]] | None = None

    for part in _candidate_parts(parts, mode, remaining):
        match = _best_placement_for_part(
            parts=parts,
            part=part,
            sheet=sheet,
            placed_polygons=placed_polygons,
            placed_count=placed_counts[part.part_id],
            rotations=rotations,
            gap=gap,
            mode=mode,
            remaining=remaining,
        )
        if match is None:
            continue

        placement, score = match
        tie_break = (float(part.polygon.area), float(remaining.get(part.part_id, 0)), part.part_id)
        if best_choice is None or score > best_choice[1] or (score == best_choice[1] and tie_break > best_choice[2]):
            best_choice = (placement, score, tie_break)

    return best_choice[0] if best_choice else None


def _part_can_fit_empty_sheet(part: PartSpec, sheets: list[SheetSpec], rotations: list[int], gap: float) -> bool:
    if not _is_nestable_part(part):
        return False
    for sheet in sheets:
        match = _best_placement_for_part(
            parts=[part],
            part=part,
            sheet=sheet,
            placed_polygons=[],
            placed_count=0,
            rotations=rotations,
            gap=gap,
            mode="batch_quantity",
            remaining={part.part_id: 1},
        )
        if match is not None:
            return True
    return False


def nest(parts: list[PartSpec], sheets: list[SheetSpec], params: dict) -> dict:
    mode = params.get("mode", "batch_quantity")
    if mode not in {"fill_sheet", "batch_quantity"}:
        raise ValueError("Unsupported nesting mode")

    gap = float(params.get("gap", 0.0))
    rotations = [rotation for rotation in params.get("rotation", [0, 180]) if rotation in {0, 90, 180, 270}] or [0]
    debug_enabled = bool(params.get("debug", False))
    source_units = params.get("source_units")
    source_max_extent = float(params["source_max_extent"]) if params.get("source_max_extent") else None

    enabled_parts = [part for part in parts if part.enabled]
    if not enabled_parts:
        raise ValueError("At least one enabled part is required")
    active_parts = [part for part in enabled_parts if _is_nestable_part(part)]

    remaining: dict[str, int] = {part.part_id: max(part.quantity, 1) for part in enabled_parts}
    placed_counts = {part.part_id: 0 for part in enabled_parts}
    area_contribution = {part.part_id: 0.0 for part in enabled_parts}
    fit_on_empty_sheet = {part.part_id: _part_can_fit_empty_sheet(part, sheets, rotations, gap) for part in enabled_parts}

    layout_map: dict[tuple[str, int], list[Placement]] = {}
    geometry_map: dict[tuple[str, int], list[Polygon]] = {}

    stop_filling = False
    for sheet, instance in _sheet_instances(sheets):
        placed_polygons = geometry_map.setdefault((sheet.sheet_id, instance), [])
        while not stop_filling:
            placement = _select_next_placement(
                parts=active_parts,
                sheet=sheet,
                placed_polygons=placed_polygons,
                placed_counts=placed_counts,
                rotations=rotations,
                gap=gap,
                mode=mode,
                remaining=remaining,
            )
            if not placement:
                break
            layout_map.setdefault((sheet.sheet_id, instance), []).append(placement)
            placed_polygons.append(placement.polygon)
            placed_counts[placement.part_id] += 1
            area_contribution[placement.part_id] += float(placement.polygon.area)
            if mode == "batch_quantity":
                remaining[placement.part_id] = max(remaining[placement.part_id] - 1, 0)
                if all(value == 0 for value in remaining.values()):
                    stop_filling = True
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

    parts_summary = {
        "total_parts": len(enabled_parts),
    }

    part_results = [
        {
            "part_id": part.part_id,
            "filename": part.filename,
            "requested_quantity": max(part.quantity, 1),
            "placed_quantity": placed_counts[part.part_id],
            "remaining_quantity": max(max(part.quantity, 1) - placed_counts[part.part_id], 0),
            "enabled": part.enabled,
            "area_contribution": area_contribution[part.part_id],
        }
        for part in enabled_parts
    ]
    part_results.sort(key=lambda item: (item["filename"] or item["part_id"], item["part_id"]))

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
    for part in enabled_parts:
        requested_quantity = max(part.quantity, 1)
        placed_quantity = placed_counts[part.part_id]
        remaining_quantity = max(requested_quantity - placed_quantity, 0)
        if not _is_nestable_part(part):
            warnings.append(
                f"Part {part.filename or part.part_id} was skipped because its geometry is invalid or zero-area after validation."
            )
            continue
        if not fit_on_empty_sheet[part.part_id]:
            warnings.append(
                f"Part {part.filename or part.part_id} does not fit within the available sheet bounds for any allowed rotation."
            )
            continue
        if mode == "batch_quantity" and remaining_quantity > 0:
            warnings.append(
                f"Part {part.filename or part.part_id} placed {placed_quantity} of {requested_quantity}; remaining quantity stays above zero because no more feasible placements fit on the available sheets."
            )
        if mode == "fill_sheet" and placed_quantity == 0:
            warnings.append(
                f"Part {part.filename or part.part_id} was enabled for Fill Sheet, but no feasible placement remained once the sheet was packed."
            )

    result = {
        "mode": mode,
        "summary": parts_summary,
        "yield": yield_value,
        "yield_ratio": yield_value,
        "scrap_ratio": scrap_ratio,
        "scrap_area": scrap_area,
        "used_area": used_area,
        "total_sheet_area": total_sheet_area,
        "parts_placed": parts_placed,
        "total_parts_placed": parts_placed,
        "layouts_used": layouts_used,
        "layouts": layouts,
        "parts": part_results,
        "unplaced_parts": unplaced,
        "warnings": warnings,
    }
    if debug_enabled:
        result["debug"] = debug_summary
    return result
