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
