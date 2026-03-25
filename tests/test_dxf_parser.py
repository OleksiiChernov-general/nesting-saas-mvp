from __future__ import annotations

from pathlib import Path

import ezdxf

from app.dxf_parser import parse_dxf


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
