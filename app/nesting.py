from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable, Literal

from shapely import affinity
from shapely.geometry import Polygon, box

from app.offcuts import summarize_job_offcuts

EPSILON = 1e-6
NestingMode = Literal["fill_sheet", "batch_quantity"]
ProgressCallback = Callable[[float, str], None]


class SearchTimeout(RuntimeError):
    pass


@dataclass
class PartSpec:
    part_id: str
    polygon: Polygon
    quantity: int
    filename: str | None = None
    enabled: bool = True
    fill_only: bool = False
    order_id: str | None = None
    order_name: str | None = None
    priority: int | None = None


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
    order_id: str | None = None
    order_name: str | None = None
    priority: int | None = None


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


def _is_axis_aligned_rectangle(polygon: Polygon) -> bool:
    if polygon.is_empty or not polygon.is_valid:
        return False
    coords = list(polygon.exterior.coords)
    if len(coords) != 5:
        return False
    min_x, min_y, max_x, max_y = polygon.bounds
    bbox_area = max(max_x - min_x, 0.0) * max(max_y - min_y, 0.0)
    return abs(bbox_area - float(polygon.area)) <= EPSILON


def _is_circle_like(polygon: Polygon) -> bool:
    if polygon.is_empty or not polygon.is_valid or polygon.area <= EPSILON:
        return False
    min_x, min_y, max_x, max_y = polygon.bounds
    width = max_x - min_x
    height = max_y - min_y
    if width <= EPSILON or height <= EPSILON:
        return False
    aspect_ratio = max(width, height) / max(min(width, height), EPSILON)
    if aspect_ratio > 1.08:
        return False
    perimeter = float(polygon.length)
    if perimeter <= EPSILON:
        return False
    compactness = (4.0 * math.pi * float(polygon.area)) / (perimeter * perimeter)
    return compactness >= 0.9


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
    for item in placed:
        if candidate.intersection(item).area > 1e-9:
            return False
        if gap > EPSILON and candidate.distance(item) < gap - EPSILON:
            return False
    return True


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise SearchTimeout("Nesting compute time limit reached")


def _report_progress(progress_callback: ProgressCallback | None, progress: float, message: str) -> None:
    if progress_callback is None:
        return
    progress_callback(max(0.0, min(progress, 0.99)), message)


def _score_layout_map(
    sheets: list[SheetSpec],
    layout_map: dict[tuple[str, int], list[Placement]],
    placed_counts: dict[str, int],
    area_contribution: dict[str, float],
) -> tuple[float, float, float, float]:
    used_area = float(sum(area_contribution.values()))
    total_parts_placed = float(sum(placed_counts.values()))
    total_sheet_area = 0.0
    layouts_used = 0.0
    for sheet, instance in _sheet_instances(sheets):
        placements = layout_map.get((sheet.sheet_id, instance), [])
        if not placements:
            continue
        layouts_used += 1.0
        total_sheet_area += float(sheet.width) * float(sheet.height)
    yield_ratio = (used_area / total_sheet_area) if total_sheet_area else 0.0
    return (yield_ratio, used_area, total_parts_placed, -layouts_used)


def _result_score(result: dict, *, mode: NestingMode, active_part_count: int) -> tuple[float, ...]:
    if mode == "fill_sheet" and active_part_count > 1:
        distinct_parts_placed = float(
            sum(1 for part in result.get("parts", []) if float(part.get("placed_quantity", 0)) > 0)
        )
        return (
            float(result.get("yield_ratio", 0.0)),
            distinct_parts_placed,
            float(result.get("used_area", 0.0)),
            float(result.get("total_parts_placed", 0.0)),
            -float(result.get("layouts_used", 0.0)),
        )

    return (
        float(result.get("yield_ratio", 0.0)),
        float(result.get("used_area", 0.0)),
        float(result.get("total_parts_placed", 0.0)),
        -float(result.get("layouts_used", 0.0)),
    )


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


def _candidate_parts(
    parts: list[PartSpec],
    mode: NestingMode,
    remaining: dict[str, int],
    *,
    strategy: str = "area_desc",
    seed_priority: dict[str, int] | None = None,
) -> list[PartSpec]:
    candidates = [part for part in parts if part.enabled and (mode == "fill_sheet" or remaining[part.part_id] > 0)]
    solo_parts = [part for part in candidates if part.fill_only]
    if mode == "fill_sheet" and solo_parts:
        candidates = solo_parts
    priority = seed_priority or {}

    if strategy == "area_asc":
        key_fn = lambda item: (round(item.polygon.area, 6), priority.get(item.part_id, 10_000), item.filename or item.part_id, item.part_id)
    elif strategy == "filename":
        key_fn = lambda item: (priority.get(item.part_id, 10_000), item.filename or item.part_id, -round(item.polygon.area, 6), item.part_id)
    elif strategy == "remaining_desc":
        key_fn = lambda item: (-remaining.get(item.part_id, 0), priority.get(item.part_id, 10_000), -round(item.polygon.area, 6), item.part_id)
    elif strategy == "seeded":
        key_fn = lambda item: (priority.get(item.part_id, 10_000), -remaining.get(item.part_id, 0), -round(item.polygon.area, 6), item.part_id)
    else:
        key_fn = lambda item: (priority.get(item.part_id, 10_000), -round(item.polygon.area, 6), item.filename or item.part_id, item.part_id)

    return sorted(candidates, key=key_fn)


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
    strategy: str,
    seed_priority: dict[str, int] | None,
    deadline: float | None,
    lookahead_enabled: bool,
) -> tuple[float, float, int, float, float, float]:
    min_x, min_y, max_x, max_y = candidate.bounds
    contact_score = _contact_score(candidate, placed_polygons, sheet, gap)
    backlog_area = float(max(remaining.get(part.part_id, 0), 1)) * float(part.polygon.area)
    primary_score = backlog_area if mode == "batch_quantity" else float(part.polygon.area)
    future_remaining = dict(remaining)
    if mode == "batch_quantity":
        future_remaining[part.part_id] = max(future_remaining.get(part.part_id, 0) - 1, 0)
    future_score = (
        _future_productive_area(
            parts=parts,
            sheet=sheet,
            placed_polygons=placed_polygons + [candidate],
            rotations=rotations,
            gap=gap,
            mode=mode,
            remaining=future_remaining,
            strategy=strategy,
            seed_priority=seed_priority,
            deadline=deadline,
        )
        if lookahead_enabled
        else 0.0
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
    strategy: str,
    seed_priority: dict[str, int] | None,
    deadline: float | None,
) -> float:
    best_area = 0.0
    for part in _candidate_parts(parts, mode, remaining, strategy=strategy, seed_priority=seed_priority):
        _check_deadline(deadline)
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
    strategy: str,
    seed_priority: dict[str, int] | None,
    deadline: float | None,
    lookahead_enabled: bool,
) -> tuple[Placement, tuple[float, float, int, float, float, float]] | None:
    best_match: tuple[Placement, tuple[float, float, int, float, float, float]] | None = None

    for rotation in rotations:
        _check_deadline(deadline)
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
                    order_id=part.order_id,
                    order_name=part.order_name,
                    priority=part.priority,
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
                    strategy=strategy,
                    seed_priority=seed_priority,
                    deadline=deadline,
                    lookahead_enabled=lookahead_enabled,
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
    strategy: str,
    seed_priority: dict[str, int] | None,
    deadline: float | None,
    lookahead_enabled: bool,
) -> Placement | None:
    best_choice: tuple[Placement, tuple[float, float, int, float, float, float], tuple[float, float, str]] | None = None

    for part in _candidate_parts(parts, mode, remaining, strategy=strategy, seed_priority=seed_priority):
        _check_deadline(deadline)
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
            strategy=strategy,
            seed_priority=seed_priority,
            deadline=deadline,
            lookahead_enabled=lookahead_enabled,
        )
        if match is None:
            continue

        placement, score = match
        tie_break = (float(part.polygon.area), float(remaining.get(part.part_id, 0)), part.part_id)
        if best_choice is None or score > best_choice[1] or (score == best_choice[1] and tie_break > best_choice[2]):
            best_choice = (placement, score, tie_break)

    return best_choice[0] if best_choice else None


def _part_can_fit_empty_sheet(part: PartSpec, sheets: list[SheetSpec], rotations: list[int], gap: float, deadline: float | None = None) -> bool:
    if not _is_nestable_part(part):
        return False
    oriented_variants = [_oriented_polygon(part.polygon, rotation) for rotation in rotations]
    for sheet in sheets:
        _check_deadline(deadline)
        if not any(
            variant.bounds[2] <= sheet.width + EPSILON and variant.bounds[3] <= sheet.height + EPSILON
            for variant in oriented_variants
        ):
            continue
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
            strategy="area_desc",
            seed_priority=None,
            deadline=deadline,
            lookahead_enabled=False,
        )
        if match is not None:
            return True
    return False


def _seed_fill_sheet_part_diversity(
    *,
    parts: list[PartSpec],
    sheet: SheetSpec,
    placed_polygons: list[Polygon],
    layout_map: dict[tuple[str, int], list[Placement]],
    layout_key: tuple[str, int],
    placed_counts: dict[str, int],
    area_contribution: dict[str, float],
    rotations: list[int],
    gap: float,
    seed_priority: dict[str, int] | None,
    deadline: float | None,
) -> None:
    for part in _candidate_parts(parts, "fill_sheet", placed_counts, strategy="area_desc", seed_priority=seed_priority):
        if placed_counts[part.part_id] > 0:
            continue
        match = _best_placement_for_part(
            parts=parts,
            part=part,
            sheet=sheet,
            placed_polygons=placed_polygons,
            placed_count=placed_counts[part.part_id],
            rotations=rotations,
            gap=gap,
            mode="fill_sheet",
            remaining=placed_counts,
            strategy="area_desc",
            seed_priority=seed_priority,
            deadline=deadline,
            lookahead_enabled=False,
        )
        if match is None:
            continue
        placement, _ = match
        layout_map.setdefault(layout_key, []).append(placement)
        placed_polygons.append(placement.polygon)
        placed_counts[placement.part_id] += 1
        area_contribution[placement.part_id] += float(placement.polygon.area)


def _grid_pack_single_part(
    *,
    part: PartSpec,
    sheets: list[SheetSpec],
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    run_number: int,
    previous_yield: float,
    enabled_parts: list[PartSpec],
    active_parts: list[PartSpec],
    debug_enabled: bool,
    source_units: str | None,
    source_max_extent: float | None,
    progress_callback: ProgressCallback | None,
    deadline: float | None,
) -> dict | None:
    best_score = (-1.0, -1.0, -1.0, 0.0)
    best_state: tuple[dict[tuple[str, int], list[Placement]], dict[str, int], dict[str, float], dict[str, int]] | None = None
    selected_part_fit = _part_can_fit_empty_sheet(part, sheets, rotations, gap, deadline)
    fit_on_empty_sheet = {item.part_id: (selected_part_fit if item.part_id == part.part_id else None) for item in enabled_parts}

    for rotation in rotations:
        _check_deadline(deadline)
        _report_progress(progress_callback, 0.16, f"Testing grid packing seed for {part.part_id} at rotation {rotation}.")
        oriented = _oriented_polygon(part.polygon, rotation)
        if not _is_axis_aligned_rectangle(oriented):
            continue

        step_x = oriented.bounds[2] + gap
        step_y = oriented.bounds[3] + gap
        if step_x <= EPSILON or step_y <= EPSILON:
            continue

        placed_counts = {item.part_id: 0 for item in enabled_parts}
        area_contribution = {item.part_id: 0.0 for item in enabled_parts}
        remaining = {item.part_id: max(item.quantity, 1) for item in enabled_parts}
        layout_map: dict[tuple[str, int], list[Placement]] = {}

        stop = False
        for sheet, instance in _sheet_instances(sheets):
            _check_deadline(deadline)
            y = 0.0
            while y + oriented.bounds[3] <= sheet.height + EPSILON and not stop:
                x = 0.0
                while x + oriented.bounds[2] <= sheet.width + EPSILON:
                    _check_deadline(deadline)
                    candidate = affinity.translate(oriented, xoff=x, yoff=y)
                    layout_map.setdefault((sheet.sheet_id, instance), []).append(
                        Placement(
                            part_id=part.part_id,
                            sheet_id=sheet.sheet_id,
                            instance=placed_counts[part.part_id] + 1,
                            rotation=rotation,
                            x=x,
                            y=y,
                            polygon=candidate,
                            order_id=part.order_id,
                            order_name=part.order_name,
                            priority=part.priority,
                        )
                    )
                    placed_counts[part.part_id] += 1
                    area_contribution[part.part_id] += float(candidate.area)
                    if mode == "batch_quantity":
                        remaining[part.part_id] = max(remaining[part.part_id] - 1, 0)
                        if remaining[part.part_id] == 0:
                            stop = True
                            break
                    x += step_x
                y += step_y
            if stop:
                break

        score = _score_layout_map(sheets, layout_map, placed_counts, area_contribution)
        if best_state is None or score > best_score:
            best_score = score
            best_state = (layout_map, placed_counts, area_contribution, remaining)

    if best_state is None:
        return None

    layout_map, placed_counts, area_contribution, remaining = best_state
    return _build_result_from_state(
        parts=enabled_parts,
        enabled_parts=enabled_parts,
        active_parts=active_parts,
        sheets=sheets,
        mode=mode,
        layout_map=layout_map,
        placed_counts=placed_counts,
        area_contribution=area_contribution,
        remaining=remaining,
        fit_on_empty_sheet=fit_on_empty_sheet,
        debug_enabled=debug_enabled,
        source_units=source_units,
        source_max_extent=source_max_extent,
        timed_out=False,
        run_number=run_number,
        previous_yield=previous_yield,
    )


def _hex_pack_single_part(
    *,
    part: PartSpec,
    sheets: list[SheetSpec],
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    run_number: int,
    previous_yield: float,
    enabled_parts: list[PartSpec],
    active_parts: list[PartSpec],
    debug_enabled: bool,
    source_units: str | None,
    source_max_extent: float | None,
    progress_callback: ProgressCallback | None,
    deadline: float | None,
) -> dict | None:
    if not _is_circle_like(part.polygon):
        return None

    oriented_cache: dict[int, Polygon] = {}
    for rotation in rotations:
        _check_deadline(deadline)
        oriented = _oriented_polygon(part.polygon, rotation)
        if any(oriented.equals_exact(existing, tolerance=1e-6) for existing in oriented_cache.values()):
            continue
        oriented_cache[rotation] = oriented

    if not oriented_cache:
        return None

    base_rotation = next(iter(oriented_cache))
    base_polygon = oriented_cache[base_rotation]
    part_width = float(base_polygon.bounds[2])
    part_height = float(base_polygon.bounds[3])
    dx = part_width + gap
    dy_candidates = [
        part_height + gap,
        max((part_height * math.sqrt(3) / 2.0), gap + 1.0),
        max(part_height * 0.82, gap + 1.0),
    ]
    offset_candidates = [0.0, dx / 2.0]
    best_score = (-1.0, -1.0, -1.0, 0.0)
    best_state: tuple[dict[tuple[str, int], list[Placement]], dict[str, int], dict[str, float], dict[str, int]] | None = None
    selected_part_fit = _part_can_fit_empty_sheet(part, sheets, [base_rotation], gap, deadline)
    fit_on_empty_sheet = {item.part_id: (selected_part_fit if item.part_id == part.part_id else None) for item in enabled_parts}

    for dy in dy_candidates:
        for row_offset in offset_candidates:
            _check_deadline(deadline)
            _report_progress(progress_callback, 0.22, f"Testing hex packing seed for {part.part_id}.")
            placed_counts = {item.part_id: 0 for item in enabled_parts}
            area_contribution = {item.part_id: 0.0 for item in enabled_parts}
            remaining = {item.part_id: max(item.quantity, 1) for item in enabled_parts}
            layout_map: dict[tuple[str, int], list[Placement]] = {}
            stop = False

            for sheet, instance in _sheet_instances(sheets):
                _check_deadline(deadline)
                placed_polygons: list[Polygon] = []
                layout_map.setdefault((sheet.sheet_id, instance), [])
                y = 0.0
                row = 0

                while y + part_height <= sheet.height + EPSILON and not stop:
                    x = row_offset if row % 2 == 1 else 0.0
                    while x + part_width <= sheet.width + EPSILON and not stop:
                        _check_deadline(deadline)
                        candidate = affinity.translate(base_polygon, xoff=x, yoff=y)
                        if _fits(candidate, placed_polygons, sheet, gap):
                            placement = Placement(
                                part_id=part.part_id,
                                sheet_id=sheet.sheet_id,
                                instance=placed_counts[part.part_id] + 1,
                                rotation=base_rotation,
                                x=x,
                                y=y,
                                polygon=candidate,
                                order_id=part.order_id,
                                order_name=part.order_name,
                                priority=part.priority,
                            )
                            layout_map[(sheet.sheet_id, instance)].append(placement)
                            placed_polygons.append(candidate)
                            placed_counts[part.part_id] += 1
                            area_contribution[part.part_id] += float(candidate.area)
                            if mode == "batch_quantity":
                                remaining[part.part_id] = max(remaining[part.part_id] - 1, 0)
                                if remaining[part.part_id] == 0:
                                    stop = True
                                    break
                        x += dx
                    y += dy
                    row += 1
                if stop:
                    break

                _refine_single_part_layout(
                    part=part,
                    sheet=sheet,
                    placements=layout_map[(sheet.sheet_id, instance)],
                    placed_count=placed_counts[part.part_id],
                    placed_counts=placed_counts,
                    area_contribution=area_contribution,
                    remaining=remaining,
                    rotations=[base_rotation],
                    gap=gap,
                    mode=mode,
                    deadline=deadline,
                )

            score = _score_layout_map(sheets, layout_map, placed_counts, area_contribution)
            if best_state is None or score > best_score:
                best_score = score
                best_state = (layout_map, placed_counts, area_contribution, remaining)

    if best_state is None:
        return None

    layout_map, placed_counts, area_contribution, remaining = best_state
    return _build_result_from_state(
        parts=enabled_parts,
        enabled_parts=enabled_parts,
        active_parts=active_parts,
        sheets=sheets,
        mode=mode,
        layout_map=layout_map,
        placed_counts=placed_counts,
        area_contribution=area_contribution,
        remaining=remaining,
        fit_on_empty_sheet=fit_on_empty_sheet,
        debug_enabled=debug_enabled,
        source_units=source_units,
        source_max_extent=source_max_extent,
        timed_out=False,
        run_number=run_number,
        previous_yield=previous_yield,
    )


def _pattern_pack_single_part(
    *,
    part: PartSpec,
    sheets: list[SheetSpec],
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    run_number: int,
    previous_yield: float,
    enabled_parts: list[PartSpec],
    active_parts: list[PartSpec],
    debug_enabled: bool,
    source_units: str | None,
    source_max_extent: float | None,
    progress_callback: ProgressCallback | None,
    deadline: float | None,
) -> dict | None:
    oriented_cache: dict[int, Polygon] = {}
    dimensions: dict[int, tuple[float, float]] = {}
    for rotation in rotations:
        _check_deadline(deadline)
        oriented = _oriented_polygon(part.polygon, rotation)
        width = float(oriented.bounds[2])
        height = float(oriented.bounds[3])
        if width <= EPSILON or height <= EPSILON:
            continue
        oriented_cache[rotation] = oriented
        dimensions[rotation] = (width, height)

    if not oriented_cache:
        return None

    unique_rotations: list[int] = []
    unique_oriented: list[Polygon] = []
    for rotation in oriented_cache:
        oriented = oriented_cache[rotation]
        if any(oriented.equals_exact(existing, tolerance=1e-6) for existing in unique_oriented):
            continue
        unique_rotations.append(rotation)
        unique_oriented.append(oriented)

    sequence_patterns = [(rotation,) for rotation in unique_rotations]
    seen_patterns = set(sequence_patterns)
    for rotation in unique_rotations:
        for offset in (180, 90, 45):
            partner = (rotation + offset) % 360
            if partner not in unique_rotations or partner == rotation:
                continue
            pattern = (rotation, partner)
            if pattern not in seen_patterns:
                sequence_patterns.append(pattern)
                seen_patterns.add(pattern)

    min_width = min(width for width, _ in dimensions.values())
    min_height = min(height for _, height in dimensions.values())
    scan_step_x = max(min_width / 4.0, gap, 1.0)
    scan_step_y = max(min_height / 4.0, gap, 1.0)
    best_score = (-1.0, -1.0, -1.0, 0.0)
    best_state: tuple[dict[tuple[str, int], list[Placement]], dict[str, int], dict[str, float], dict[str, int]] | None = None
    selected_part_fit = _part_can_fit_empty_sheet(part, sheets, rotations, gap, deadline)
    fit_on_empty_sheet = {item.part_id: (selected_part_fit if item.part_id == part.part_id else None) for item in enabled_parts}

    for pattern in sequence_patterns:
        first_width = dimensions[pattern[0]][0]
        offset_options = [0.0]
        staggered_offset = (first_width + gap) / 2.0
        if staggered_offset > EPSILON:
            offset_options.append(staggered_offset)

        for odd_row_offset in offset_options:
            _check_deadline(deadline)
            _report_progress(progress_callback, 0.24, f"Testing pattern packing seed for {part.part_id}.")
            placed_counts = {item.part_id: 0 for item in enabled_parts}
            area_contribution = {item.part_id: 0.0 for item in enabled_parts}
            remaining = {item.part_id: max(item.quantity, 1) for item in enabled_parts}
            layout_map: dict[tuple[str, int], list[Placement]] = {}
            stop = False

            for sheet, instance in _sheet_instances(sheets):
                _check_deadline(deadline)
                placed_polygons: list[Polygon] = []
                layout_map.setdefault((sheet.sheet_id, instance), [])
                y = 0.0
                row_index = 0

                while y <= sheet.height + EPSILON and not stop:
                    _check_deadline(deadline)
                    x = odd_row_offset if row_index % 2 == 1 else 0.0
                    row_height = 0.0
                    placed_in_row = False
                    sequence_index = 0

                    while x <= sheet.width + EPSILON and not stop:
                        _check_deadline(deadline)
                        preferred_rotation = pattern[sequence_index % len(pattern)]
                        trial_rotations = [preferred_rotation] + [rotation for rotation in unique_rotations if rotation != preferred_rotation]
                        placed_here = False

                        for rotation in trial_rotations:
                            oriented = oriented_cache[rotation]
                            part_width, part_height = dimensions[rotation]
                            if x + part_width > sheet.width + EPSILON or y + part_height > sheet.height + EPSILON:
                                continue
                            candidate = affinity.translate(oriented, xoff=x, yoff=y)
                            if not _fits(candidate, placed_polygons, sheet, gap):
                                continue

                            placement = Placement(
                                part_id=part.part_id,
                                sheet_id=sheet.sheet_id,
                                instance=placed_counts[part.part_id] + 1,
                                rotation=rotation,
                                x=x,
                                y=y,
                                polygon=candidate,
                                order_id=part.order_id,
                                order_name=part.order_name,
                                priority=part.priority,
                            )
                            placed_polygons.append(candidate)
                            placed_in_row = True
                            row_height = max(row_height, part_height)
                            layout_map[(sheet.sheet_id, instance)].append(placement)
                            placed_counts[part.part_id] += 1
                            area_contribution[part.part_id] += float(candidate.area)
                            if mode == "batch_quantity":
                                remaining[part.part_id] = max(remaining[part.part_id] - 1, 0)
                                if remaining[part.part_id] == 0:
                                    stop = True
                            x = float(candidate.bounds[2]) + gap
                            sequence_index += 1
                            placed_here = True
                            break

                        if not placed_here:
                            x += scan_step_x

                    if placed_in_row:
                        y += row_height + gap
                    else:
                        y += scan_step_y
                    row_index += 1

                if stop:
                    break

            score = _score_layout_map(sheets, layout_map, placed_counts, area_contribution)
            if best_state is None or score > best_score:
                best_score = score
                best_state = (layout_map, placed_counts, area_contribution, remaining)
            if score[0] >= 0.85:
                break
        if best_score[0] >= 0.85:
            break

    if best_state is None:
        return None

    layout_map, placed_counts, area_contribution, remaining = best_state
    return _build_result_from_state(
        parts=enabled_parts,
        enabled_parts=enabled_parts,
        active_parts=active_parts,
        sheets=sheets,
        mode=mode,
        layout_map=layout_map,
        placed_counts=placed_counts,
        area_contribution=area_contribution,
        remaining=remaining,
        fit_on_empty_sheet=fit_on_empty_sheet,
        debug_enabled=debug_enabled,
        source_units=source_units,
        source_max_extent=source_max_extent,
        timed_out=False,
        run_number=run_number,
        previous_yield=previous_yield,
    )


def _refine_single_part_layout(
    *,
    part: PartSpec,
    sheet: SheetSpec,
    placements: list[Placement],
    placed_count: int,
    placed_counts: dict[str, int],
    area_contribution: dict[str, float],
    remaining: dict[str, int],
    rotations: list[int],
    gap: float,
    mode: NestingMode,
    deadline: float | None,
    max_new_placements: int = 4,
    time_slice_sec: float = 0.05,
) -> None:
    if max_new_placements <= 0 or not placements:
        return

    refine_deadline = min(deadline, time.monotonic() + time_slice_sec) if deadline is not None else time.monotonic() + time_slice_sec
    placed_polygons = [item.polygon for item in placements]
    added = 0

    try:
        while added < max_new_placements:
            _check_deadline(refine_deadline)
            match = _best_placement_for_part(
                parts=[part],
                part=part,
                sheet=sheet,
                placed_polygons=placed_polygons,
                placed_count=placed_count + added,
                rotations=rotations,
                gap=gap,
                mode=mode,
                remaining=remaining,
                strategy="area_desc",
                seed_priority=None,
                deadline=refine_deadline,
                lookahead_enabled=False,
            )
            if match is None:
                break

            placement, _ = match
            placements.append(placement)
            placed_polygons.append(placement.polygon)
            placed_counts[part.part_id] += 1
            area_contribution[part.part_id] += float(placement.polygon.area)
            added += 1
            if mode == "batch_quantity":
                remaining[part.part_id] = max(remaining[part.part_id] - 1, 0)
                if remaining[part.part_id] == 0:
                    break
    except SearchTimeout:
        return


def _build_result_from_state(
    *,
    parts: list[PartSpec],
    enabled_parts: list[PartSpec],
    active_parts: list[PartSpec],
    sheets: list[SheetSpec],
    mode: NestingMode,
    layout_map: dict[tuple[str, int], list[Placement]],
    placed_counts: dict[str, int],
    area_contribution: dict[str, float],
    remaining: dict[str, int],
    fit_on_empty_sheet: dict[str, bool | None],
    debug_enabled: bool,
    source_units: str | None,
    source_max_extent: float | None,
    timed_out: bool,
    run_number: int,
    previous_yield: float,
) -> dict:
    batch_orders: dict[str, dict[str, object]] = {}
    for part in enabled_parts:
        if not part.order_id:
            continue
        order_entry = batch_orders.setdefault(
            part.order_id,
            {
                "order_id": part.order_id,
                "order_name": part.order_name,
                "priority": part.priority,
                "part_ids": [],
            },
        )
        if part.order_name and not order_entry.get("order_name"):
            order_entry["order_name"] = part.order_name
        if part.priority is not None and order_entry.get("priority") is None:
            order_entry["priority"] = part.priority
        order_entry["part_ids"].append(part.part_id)

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
    offcuts, offcut_summary = summarize_job_offcuts(layouts)

    parts_summary = {"total_parts": len(enabled_parts)}
    part_results = [
        {
            "part_id": part.part_id,
            "filename": part.filename,
            "requested_quantity": max(part.quantity, 1),
            "placed_quantity": placed_counts[part.part_id],
            "remaining_quantity": max(max(part.quantity, 1) - placed_counts[part.part_id], 0),
            "enabled": part.enabled,
            "area_contribution": area_contribution[part.part_id],
            "order_id": part.order_id,
            "order_name": part.order_name,
            "priority": part.priority,
        }
        for part in enabled_parts
    ]
    part_results.sort(key=lambda item: (item["filename"] or item["part_id"], item["part_id"]))

    unplaced = sorted([part_id for part_id, count in remaining.items() if count > 0]) if mode == "batch_quantity" else []
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
    if timed_out:
        warnings.append("Optimization stopped at the 60-second compute limit and returned the best valid layout found so far.")
    for part in enabled_parts:
        requested_quantity = max(part.quantity, 1)
        placed_quantity = placed_counts[part.part_id]
        remaining_quantity = max(requested_quantity - placed_quantity, 0)
        if not _is_nestable_part(part):
            warnings.append(
                f"Part {part.filename or part.part_id} was skipped because its geometry is invalid or zero-area after validation."
            )
            continue
        if fit_on_empty_sheet.get(part.part_id) is False:
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

    status = "SUCCEEDED"
    if timed_out or (mode == "batch_quantity" and any(value > 0 for value in remaining.values())):
        status = "PARTIAL"
    if parts_placed == 0 and any(fit_on_empty_sheet.get(part.part_id) is False for part in enabled_parts):
        status = "PARTIAL"

    result = {
        "status": status,
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
        "batch": {
            "batch_id": f"batch-run-{run_number}",
            "batch_name": f"Batch Run {run_number}",
            "orders": sorted(batch_orders.values(), key=lambda item: (str(item["order_name"] or item["order_id"]), str(item["order_id"]))),
        },
        "offcuts": offcuts,
        "offcut_summary": offcut_summary,
        "unplaced_parts": unplaced,
        "warnings": warnings,
        "run_number": run_number,
        "previous_yield": previous_yield,
        "best_yield": max(previous_yield, yield_value),
        "improvement_percent": 0.0,
        "timed_out": timed_out,
    }
    if debug_enabled:
        result["debug"] = debug_summary
    return result


def nest(parts: list[PartSpec], sheets: list[SheetSpec], params: dict) -> dict:
    mode = params.get("mode", "batch_quantity")
    if mode not in {"fill_sheet", "batch_quantity"}:
        raise ValueError("Unsupported nesting mode")

    gap = float(params.get("gap", 0.0))
    packing_gap = 0.0 if mode == "fill_sheet" else gap
    rotations = [rotation for rotation in params.get("rotation", [0, 45, 90, 135, 180, 225, 270, 315]) if rotation in {0, 45, 90, 135, 180, 225, 270, 315}] or [0]
    debug_enabled = bool(params.get("debug", False))
    source_units = params.get("source_units")
    source_max_extent = float(params["source_max_extent"]) if params.get("source_max_extent") else None
    time_limit_sec = max(float(params.get("time_limit_sec", 60.0)), 0.01)
    deadline = time.monotonic() + time_limit_sec
    run_number = max(int(params.get("run_number", 1)), 1)
    previous_result = params.get("previous_result") if isinstance(params.get("previous_result"), dict) else None
    previous_yield = float(previous_result.get("yield_ratio") or previous_result.get("yield") or 0.0) if previous_result else 0.0
    progress_callback = params.get("progress_callback") if callable(params.get("progress_callback")) else None
    seed_priority = (
        {
            str(item.get("part_id")): index
            for index, item in enumerate(
                sorted(
                    previous_result.get("parts", []),
                    key=lambda value: (
                        -float(value.get("area_contribution", 0.0)),
                        -float(value.get("placed_quantity", 0.0)),
                        str(value.get("part_id", "")),
                    ),
                )
            )
        }
        if previous_result
        else {}
    )

    enabled_parts = [part for part in parts if part.enabled]
    if not enabled_parts:
        raise ValueError("At least one enabled part is required")
    active_parts = [part for part in enabled_parts if _is_nestable_part(part)]
    placement_parts = _candidate_parts(
        active_parts,
        mode,
        {part.part_id: max(part.quantity, 1) for part in active_parts},
        strategy="area_desc",
        seed_priority=seed_priority,
    )

    fit_on_empty_sheet: dict[str, bool | None] = {}
    _report_progress(progress_callback, 0.05, "Checking empty-sheet feasibility for enabled parts.")
    for index, part in enumerate(enabled_parts, start=1):
        try:
            fit_on_empty_sheet[part.part_id] = _part_can_fit_empty_sheet(part, sheets, rotations, packing_gap, deadline)
        except SearchTimeout:
            fit_on_empty_sheet[part.part_id] = None
        _report_progress(
            progress_callback,
            0.05 + (0.1 * index / max(len(enabled_parts), 1)),
            f"Checked empty-sheet feasibility for {part.part_id}.",
        )
    strategy_cycle = ["area_desc", "remaining_desc", "seeded", "filename", "area_asc"]
    best_result: dict | None = None
    best_score = (-1.0, -1.0, -1.0, 0.0)
    pass_index = 0
    timed_out = False
    stagnant_passes = 0

    try:
        for part in placement_parts:
            grid_result = _grid_pack_single_part(
                part=part,
                sheets=sheets,
                rotations=rotations,
                gap=packing_gap,
                mode=mode,
                run_number=run_number,
                previous_yield=previous_yield,
                enabled_parts=enabled_parts,
                active_parts=placement_parts,
                debug_enabled=debug_enabled,
                source_units=source_units,
                source_max_extent=source_max_extent,
                progress_callback=progress_callback,
                deadline=deadline,
            )
            if grid_result is None:
                continue
            grid_score = _result_score(grid_result, mode=mode, active_part_count=len(active_parts))
            if best_result is None or grid_score > best_score:
                best_result = grid_result
                best_score = grid_score
            if len(placement_parts) == 1 and grid_result.get("yield_ratio", 0.0) >= 0.85:
                return grid_result
        if mode == "fill_sheet" and len(placement_parts) == 1:
            hex_result = _hex_pack_single_part(
                part=placement_parts[0],
                sheets=sheets,
                rotations=rotations,
                gap=packing_gap,
                mode=mode,
                run_number=run_number,
                previous_yield=previous_yield,
                enabled_parts=enabled_parts,
                active_parts=placement_parts,
                debug_enabled=debug_enabled,
                source_units=source_units,
                source_max_extent=source_max_extent,
                progress_callback=progress_callback,
                deadline=deadline,
            )
            if hex_result is not None:
                hex_score = _result_score(hex_result, mode=mode, active_part_count=len(placement_parts))
                if best_result is None or hex_score > best_score:
                    best_result = hex_result
                    best_score = hex_score
                if hex_result.get("yield_ratio", 0.0) >= 0.85:
                    return hex_result
            pattern_result = _pattern_pack_single_part(
                part=placement_parts[0],
                sheets=sheets,
                rotations=rotations,
                gap=packing_gap,
                mode=mode,
                run_number=run_number,
                previous_yield=previous_yield,
                enabled_parts=enabled_parts,
                active_parts=placement_parts,
                debug_enabled=debug_enabled,
                source_units=source_units,
                source_max_extent=source_max_extent,
                progress_callback=progress_callback,
                deadline=deadline,
            )
            if pattern_result is not None:
                pattern_score = _result_score(pattern_result, mode=mode, active_part_count=len(placement_parts))
                if best_result is None or pattern_score > best_score:
                    best_result = pattern_result
                    best_score = pattern_score
                if pattern_result.get("yield_ratio", 0.0) >= 0.85:
                    return pattern_result
    except SearchTimeout:
        timed_out = True

    while time.monotonic() < deadline:
        strategy = strategy_cycle[(run_number + pass_index - 1) % len(strategy_cycle)]
        lookahead_enabled = mode == "batch_quantity" and pass_index % 2 == 0 and len(placement_parts) > 1
        remaining: dict[str, int] = {part.part_id: max(part.quantity, 1) for part in enabled_parts}
        placed_counts = {part.part_id: 0 for part in enabled_parts}
        area_contribution = {part.part_id: 0.0 for part in enabled_parts}
        layout_map: dict[tuple[str, int], list[Placement]] = {}
        geometry_map: dict[tuple[str, int], list[Polygon]] = {}
        stop_filling = False

        try:
            for sheet, instance in _sheet_instances(sheets):
                _check_deadline(deadline)
                placed_polygons = geometry_map.setdefault((sheet.sheet_id, instance), [])
                if mode == "fill_sheet" and len(placement_parts) > 1 and not any(placed_counts.values()):
                    _seed_fill_sheet_part_diversity(
                        parts=placement_parts,
                        sheet=sheet,
                        placed_polygons=placed_polygons,
                        layout_map=layout_map,
                        layout_key=(sheet.sheet_id, instance),
                        placed_counts=placed_counts,
                        area_contribution=area_contribution,
                        rotations=rotations,
                        gap=packing_gap,
                        seed_priority=seed_priority,
                        deadline=deadline,
                    )
                while not stop_filling:
                    _check_deadline(deadline)
                    placement = _select_next_placement(
                        parts=placement_parts,
                        sheet=sheet,
                        placed_polygons=placed_polygons,
                        placed_counts=placed_counts,
                        rotations=rotations,
                        gap=packing_gap,
                        mode=mode,
                        remaining=remaining,
                        strategy=strategy,
                        seed_priority=seed_priority,
                        deadline=deadline,
                        lookahead_enabled=lookahead_enabled,
                    )
                    if not placement:
                        break
                    layout_map.setdefault((sheet.sheet_id, instance), []).append(placement)
                    placed_polygons.append(placement.polygon)
                    placed_counts[placement.part_id] += 1
                    area_contribution[placement.part_id] += float(placement.polygon.area)
                    if progress_callback and sum(placed_counts.values()) % 5 == 0:
                        progress_callback(
                            min(sum(placed_counts.values()) / max(len(enabled_parts) * 8, 1), 0.99),
                            f"Optimization pass {pass_index + 1}: testing {strategy} placement strategy.",
                        )
                    if mode == "batch_quantity":
                        remaining[placement.part_id] = max(remaining[placement.part_id] - 1, 0)
                        if all(value == 0 for value in remaining.values()):
                            stop_filling = True
                if stop_filling:
                    break
        except SearchTimeout:
            timed_out = True

        candidate_result = _build_result_from_state(
            parts=parts,
            enabled_parts=enabled_parts,
            active_parts=placement_parts,
            sheets=sheets,
            mode=mode,
            layout_map=layout_map,
            placed_counts=placed_counts,
            area_contribution=area_contribution,
            remaining=remaining,
            fit_on_empty_sheet=fit_on_empty_sheet,
            debug_enabled=debug_enabled,
            source_units=source_units,
            source_max_extent=source_max_extent,
            timed_out=timed_out,
            run_number=run_number,
            previous_yield=previous_yield,
        )
        candidate_score = _result_score(candidate_result, mode=mode, active_part_count=len(placement_parts))
        improved = best_result is None or candidate_score > best_score
        if improved:
            best_result = candidate_result
            best_score = candidate_score
            stagnant_passes = 0
        else:
            stagnant_passes += 1

        if not timed_out and candidate_result.get("status") == "SUCCEEDED":
            break
        if mode == "batch_quantity" and not timed_out and stagnant_passes >= 1:
            # Batch quantity jobs often hit a stable partial layout quickly; once an
            # additional pass fails to improve the score, return the best known result
            # instead of burning the full deadline budget inside the subprocess wrapper.
            break
        if timed_out:
            break
        pass_index += 1

    if best_result is None:
        zero_remaining = {part.part_id: max(part.quantity, 1) for part in enabled_parts}
        best_result = _build_result_from_state(
            parts=parts,
            enabled_parts=enabled_parts,
            active_parts=placement_parts,
            sheets=sheets,
            mode=mode,
            layout_map={},
            placed_counts={part.part_id: 0 for part in enabled_parts},
            area_contribution={part.part_id: 0.0 for part in enabled_parts},
            remaining=zero_remaining,
            fit_on_empty_sheet=fit_on_empty_sheet,
            debug_enabled=debug_enabled,
            source_units=source_units,
            source_max_extent=source_max_extent,
            timed_out=True,
            run_number=run_number,
            previous_yield=previous_yield,
        )
    return best_result
