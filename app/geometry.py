from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, snap, unary_union


@dataclass
class CleanupIssue:
    source: str
    reason: str


def polygon_from_points(points: list[tuple[float, float]]) -> Polygon:
    polygon = Polygon(points)
    if polygon.is_empty or polygon.area <= 0 or not polygon.is_valid:
        raise ValueError("Degenerate polygon")
    return polygon


def close_ring(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return points
    return points if points[0] == points[-1] else [*points, points[0]]


def polygon_to_points(polygon: Polygon) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in polygon.exterior.coords]


def clean_geometry(polygons: list[Polygon], tolerance: float) -> tuple[list[Polygon], list[CleanupIssue]]:
    issues: list[CleanupIssue] = []
    cleaned: list[Polygon] = []

    for index, polygon in enumerate(polygons):
        if not polygon.is_valid:
            issues.append(CleanupIssue(source=f"polygon[{index}]", reason="Input polygon has self-intersections"))
            continue
        boundary = polygon.boundary
        snapped = snap(boundary, boundary, tolerance)
        merged = unary_union(snapped)
        rebuilt = list(polygonize(merged))
        candidate = max(rebuilt, key=lambda item: item.area, default=polygon)
        candidate = candidate.buffer(0)

        if candidate.geom_type != "Polygon":
            issues.append(CleanupIssue(source=f"polygon[{index}]", reason="Self-intersection could not be repaired"))
            continue
        if not candidate.is_valid:
            issues.append(CleanupIssue(source=f"polygon[{index}]", reason="Invalid polygon after cleanup"))
            continue
        cleaned.append(candidate)

    unique: list[Polygon] = []
    seen = set()
    for polygon in cleaned:
        signature = tuple((round(x, 6), round(y, 6)) for x, y in polygon.exterior.coords)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(polygon)

    return unique, issues


def dedupe_segments(segments: list[LineString]) -> list[LineString]:
    unique: list[LineString] = []
    seen = set()
    for segment in segments:
        coords = list(segment.coords)
        if len(coords) != 2:
            continue
        a = tuple(round(value, 6) for value in coords[0])
        b = tuple(round(value, 6) for value in coords[1])
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(segment)
    return unique
