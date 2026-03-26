from __future__ import annotations

from pathlib import Path

import ezdxf

from app.dxf_parser import audit_dxf_geometry, parse_dxf, parse_dxf_with_audit
from app.services import import_dxf


def test_parse_dxf_returns_closed_polygon_and_invalid_shapes(tmp_path: Path):
    file_path = tmp_path / "sample.dxf"
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_line((10, 10), (0, 10))
    msp.add_line((0, 10), (0, 0))
    msp.add_line((5, 5), (5, 5))
    doc.saveas(file_path)

    polygons, invalid_shapes = parse_dxf(file_path)

    assert len(polygons) == 1
    assert list(polygons[0].exterior.coords)[0] == list(polygons[0].exterior.coords)[-1]
    assert any(item.reason == "Zero-length segment" for item in invalid_shapes)


def test_parse_dxf_recovers_near_closed_open_polyline(tmp_path: Path):
    file_path = tmp_path / "near_closed.dxf"
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10), (0.2, 0.1)], close=False)
    doc.saveas(file_path)

    polygons, invalid_shapes = parse_dxf(file_path, tolerance=0.5)

    assert len(polygons) == 1
    assert polygons[0].area > 0
    assert invalid_shapes == []


def test_audit_dxf_geometry_reports_inches_warning(tmp_path: Path):
    file_path = tmp_path / "inches_circle.dxf"
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    doc.header["$MEASUREMENT"] = 0
    msp = doc.modelspace()
    msp.add_circle((0, 0), radius=3.5)
    doc.saveas(file_path)

    polygons, _ = parse_dxf(file_path)
    audit = audit_dxf_geometry(file_path, polygons)

    assert audit.detected_units == "Inches"
    assert audit.measurement_system == "Imperial"
    assert audit.geometry_stats["polygon_count"] == 1
    assert audit.geometry_stats["max_extent"] is not None
    assert any("Enter sheet dimensions in the same units" in warning for warning in audit.warnings)


def test_parse_dxf_with_audit_preserves_units_without_second_parse(tmp_path: Path):
    file_path = tmp_path / "single_read_audit.dxf"
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True)
    doc.saveas(file_path)

    result = parse_dxf_with_audit(file_path)

    assert len(result.polygons) == 1
    assert result.audit.detected_units == "Millimeters"
    assert result.audit.measurement_system == "Metric"
    assert result.audit.geometry_stats["polygon_count"] == 1


def test_import_dxf_reads_source_file_once(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "count_reads.dxf"
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (8, 0), (8, 4), (0, 4)], close=True)
    doc.saveas(file_path)

    real_readfile = ezdxf.readfile
    call_count = 0

    def counting_readfile(path: str):
        nonlocal call_count
        call_count += 1
        return real_readfile(path)

    monkeypatch.setattr("app.dxf_parser.ezdxf.readfile", counting_readfile)

    response = import_dxf(str(file_path), "count_reads.dxf", "imp-test", tolerance=0.5)

    assert response.audit is not None
    assert response.audit.geometry_stats.polygon_count == 1
    assert call_count == 1
