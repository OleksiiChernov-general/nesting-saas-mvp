from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, snap, unary_union

from app.geometry import clean_geometry, dedupe_segments


@dataclass
class InvalidShapeReport:
    source: str
    reason: str


def _arc_points(center: tuple[float, float], radius: float, start_angle: float, end_angle: float) -> list[tuple[float, float]]:
    if end_angle < start_angle:
        end_angle += 360.0
    sweep = end_angle - start_angle
    steps = max(8, int(abs(sweep) / 10) + 1)
    points = []
    for index in range(steps + 1):
        angle = math.radians(start_angle + (sweep * index / steps))
        points.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
    return points


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.dist(a, b)


def _close_points(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    if points[0] == points[-1]:
        return points
    if _distance(points[0], points[-1]) <= tolerance:
        return [*points, points[0]]
    return points


def _segments_from_points(points: list[tuple[float, float]]) -> list[LineString]:
    return [LineString([points[index], points[index + 1]]) for index in range(len(points) - 1) if points[index] != points[index + 1]]


def _flattened_points(entity, tolerance: float) -> list[tuple[float, float]]:
    return [(float(point.x), float(point.y)) for point in entity.flattening(max(tolerance, 0.1))]


def _append_polygon_or_segments(
    points: list[tuple[float, float]],
    *,
    source: str,
    polygons: list[Polygon],
    segments: list[LineString],
    invalid: list[InvalidShapeReport],
    tolerance: float,
    force_close: bool = False,
) -> None:
    if len(points) < 2:
        invalid.append(InvalidShapeReport(source=source, reason="Not enough vertices"))
        return

    candidate_points = points
    if force_close:
        candidate_points = points if points[0] == points[-1] else [*points, points[0]]
    else:
        candidate_points = _close_points(points, tolerance)

    if len(candidate_points) >= 4 and candidate_points[0] == candidate_points[-1]:
        polygon = Polygon(candidate_points)
        if polygon.is_valid and polygon.area > 0:
            polygons.append(polygon)
            return

    segments.extend(_segments_from_points(candidate_points))


def parse_dxf(file_path: str | Path, tolerance: float = 0.5) -> tuple[list[Polygon], list[InvalidShapeReport]]:
    document = ezdxf.readfile(str(file_path))
    modelspace = document.modelspace()
    polygons: list[Polygon] = []
    segments: list[LineString] = []
    invalid: list[InvalidShapeReport] = []

    for index, entity in enumerate(modelspace):
        dxftype = entity.dxftype()

        if dxftype == "LINE":
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            if start == end:
                invalid.append(InvalidShapeReport(source=f"LINE[{index}]", reason="Zero-length segment"))
                continue
            segments.append(LineString([start, end]))
            continue

        if dxftype == "ARC":
            arc_points = _arc_points(
                (entity.dxf.center.x, entity.dxf.center.y),
                float(entity.dxf.radius),
                float(entity.dxf.start_angle),
                float(entity.dxf.end_angle),
            )
            segments.extend(LineString([arc_points[i], arc_points[i + 1]]) for i in range(len(arc_points) - 1))
            continue

        if dxftype == "CIRCLE":
            _append_polygon_or_segments(
                _arc_points((entity.dxf.center.x, entity.dxf.center.y), float(entity.dxf.radius), 0.0, 360.0),
                source=f"CIRCLE[{index}]",
                polygons=polygons,
                segments=segments,
                invalid=invalid,
                tolerance=tolerance,
                force_close=True,
            )
            continue

        if dxftype in {"POLYLINE", "LWPOLYLINE"}:
            points = [(float(x), float(y)) for x, y, *_ in entity.get_points()]
            _append_polygon_or_segments(
                points,
                source=f"{dxftype}[{index}]",
                polygons=polygons,
                segments=segments,
                invalid=invalid,
                tolerance=tolerance,
                force_close=bool(entity.is_closed),
            )
            continue

        if dxftype in {"ELLIPSE", "SPLINE"}:
            try:
                flattened = _flattened_points(entity, tolerance)
            except Exception:
                invalid.append(InvalidShapeReport(source=f"{dxftype}[{index}]", reason="Could not flatten entity"))
                continue
            _append_polygon_or_segments(
                flattened,
                source=f"{dxftype}[{index}]",
                polygons=polygons,
                segments=segments,
                invalid=invalid,
                tolerance=tolerance,
            )
            continue

        invalid.append(InvalidShapeReport(source=f"{dxftype}[{index}]", reason="Unsupported entity"))

    if segments:
        merged = unary_union(dedupe_segments(segments))
        snapped = snap(merged, merged, tolerance)
        polygons.extend(poly for poly in polygonize(unary_union(snapped)) if poly.is_valid and poly.area > 0)

    cleaned, cleanup_issues = clean_geometry(polygons, tolerance=tolerance)
    invalid.extend(InvalidShapeReport(source=issue.source, reason=issue.reason) for issue in cleanup_issues)
    return cleaned, invalid
