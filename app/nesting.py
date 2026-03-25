from __future__ import annotations

from dataclasses import dataclass

from shapely import affinity
from shapely.geometry import Polygon, box


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


def nest(parts: list[PartSpec], sheets: list[SheetSpec], params: dict) -> dict:
    gap = float(params.get("gap", 0.0))
    rotations = [rotation for rotation in params.get("rotation", [0, 180]) if rotation in {0, 180}] or [0]

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
    layouts.sort(key=lambda item: (item["sheet_id"], item["instance"]))
    for layout in layouts:
        layout["placements"].sort(key=lambda item: (item.y, item.x, item.part_id, item.instance))

    return {
        "yield": yield_value,
        "scrap_area": scrap_area,
        "used_area": used_area,
        "total_sheet_area": total_sheet_area,
        "layouts": layouts,
        "unplaced_parts": unplaced,
    }
