from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

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

        if dxftype in {"POLYLINE", "LWPOLYLINE"}:
            points = [(float(x), float(y)) for x, y, *_ in entity.get_points()]
            if len(points) < 3:
                invalid.append(InvalidShapeReport(source=f"{dxftype}[{index}]", reason="Not enough vertices"))
                continue
            is_closed = bool(entity.is_closed)
            if is_closed:
                ring = points if points[0] == points[-1] else [*points, points[0]]
                polygon = Polygon(ring)
                if polygon.is_valid and polygon.area > 0:
                    polygons.append(polygon)
                else:
                    invalid.append(InvalidShapeReport(source=f"{dxftype}[{index}]", reason="Invalid closed polyline"))
                continue

            segments.extend(LineString([points[i], points[i + 1]]) for i in range(len(points) - 1))
            invalid.append(InvalidShapeReport(source=f"{dxftype}[{index}]", reason="Open polyline was not returned as polygon"))
            continue

        invalid.append(InvalidShapeReport(source=f"{dxftype}[{index}]", reason="Unsupported entity"))

    merged = unary_union(dedupe_segments(segments))
    polygons.extend(poly for poly in polygonize(merged) if poly.is_valid and poly.area > 0)

    cleaned, cleanup_issues = clean_geometry(polygons, tolerance=tolerance)
    invalid.extend(InvalidShapeReport(source=issue.source, reason=issue.reason) for issue in cleanup_issues)
    return cleaned, invalid
