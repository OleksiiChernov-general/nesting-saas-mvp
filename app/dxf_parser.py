from __future__ import annotations

import math
import statistics
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


UNIT_MAP = {
    0: "Unitless",
    1: "Inches",
    2: "Feet",
    3: "Miles",
    4: "Millimeters",
    5: "Centimeters",
    6: "Meters",
    7: "Kilometers",
    8: "Microinches",
    9: "Mils",
    10: "Yards",
    11: "Angstroms",
    12: "Nanometers",
    13: "Microns",
    14: "Decimeters",
    15: "Decameters",
    16: "Hectometers",
    17: "Gigameters",
    18: "Astronomical units",
    19: "Light years",
    20: "Parsecs",
}


@dataclass
class DXFAudit:
    units_code: int | None
    detected_units: str | None
    measurement_system: str | None
    source_bounds: dict | None
    geometry_stats: dict
    warnings: list[str]


@dataclass
class DXFImportParseResult:
    polygons: list[Polygon]
    invalid_shapes: list[InvalidShapeReport]
    audit: DXFAudit


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


def _bounds_dict(bounds: tuple[float, float, float, float]) -> dict[str, float]:
    min_x, min_y, max_x, max_y = bounds
    return {
        "min_x": float(min_x),
        "min_y": float(min_y),
        "max_x": float(max_x),
        "max_y": float(max_y),
        "width": float(max_x - min_x),
        "height": float(max_y - min_y),
    }


def _build_dxf_audit(
    polygons: list[Polygon],
    *,
    units_code: int | None,
    measurement_raw: int | None,
) -> DXFAudit:
    measurement_system = (
        "Metric" if measurement_raw == 1 else "Imperial" if measurement_raw == 0 else None
    )

    widths = [poly.bounds[2] - poly.bounds[0] for poly in polygons]
    heights = [poly.bounds[3] - poly.bounds[1] for poly in polygons]
    areas = [poly.area for poly in polygons]
    source_bounds = None
    if polygons:
        source_bounds = _bounds_dict(
            (
                min(poly.bounds[0] for poly in polygons),
                min(poly.bounds[1] for poly in polygons),
                max(poly.bounds[2] for poly in polygons),
                max(poly.bounds[3] for poly in polygons),
            )
        )

    max_extent = max([*widths, *heights], default=0.0)
    geometry_stats = {
        "polygon_count": len(polygons),
        "total_area": float(sum(areas)),
        "min_width": float(min(widths)) if widths else None,
        "median_width": float(statistics.median(widths)) if widths else None,
        "max_width": float(max(widths)) if widths else None,
        "min_height": float(min(heights)) if heights else None,
        "median_height": float(statistics.median(heights)) if heights else None,
        "max_height": float(max(heights)) if heights else None,
        "min_area": float(min(areas)) if areas else None,
        "median_area": float(statistics.median(areas)) if areas else None,
        "max_area": float(max(areas)) if areas else None,
        "max_extent": float(max_extent) if polygons else None,
    }

    warnings: list[str] = []
    detected_units = UNIT_MAP.get(units_code) if units_code is not None else None
    if detected_units in {"Inches", "Feet", "Yards"}:
        warnings.append(f"DXF units are {detected_units}. Enter sheet dimensions in the same units or convert them before nesting.")
    elif detected_units in {None, "Unitless"}:
        warnings.append("DXF units are missing or unitless. Verify that sheet dimensions use the same scale before nesting.")

    return DXFAudit(
        units_code=units_code,
        detected_units=detected_units,
        measurement_system=measurement_system,
        source_bounds=source_bounds,
        geometry_stats=geometry_stats,
        warnings=warnings,
    )


def audit_dxf_geometry(file_path: str | Path, polygons: list[Polygon]) -> DXFAudit:
    document = ezdxf.readfile(str(file_path))
    return _build_dxf_audit(
        polygons,
        units_code=document.header.get("$INSUNITS"),
        measurement_raw=document.header.get("$MEASUREMENT"),
    )


def _parse_dxf_document(document, tolerance: float) -> tuple[list[Polygon], list[InvalidShapeReport]]:
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


def parse_dxf_with_audit(file_path: str | Path, tolerance: float = 0.5) -> DXFImportParseResult:
    document = ezdxf.readfile(str(file_path))
    polygons, invalid = _parse_dxf_document(document, tolerance)
    audit = _build_dxf_audit(
        polygons,
        units_code=document.header.get("$INSUNITS"),
        measurement_raw=document.header.get("$MEASUREMENT"),
    )
    return DXFImportParseResult(polygons=polygons, invalid_shapes=invalid, audit=audit)


def parse_dxf(file_path: str | Path, tolerance: float = 0.5) -> tuple[list[Polygon], list[InvalidShapeReport]]:
    result = parse_dxf_with_audit(file_path, tolerance)
    return result.polygons, result.invalid_shapes
