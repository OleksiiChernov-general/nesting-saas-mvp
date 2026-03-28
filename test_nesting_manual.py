#!/usr/bin/env python
"""Quick manual test of nesting algorithm."""
import sys
sys.path.insert(0, '.')

from shapely.geometry import Polygon
from app.nesting import PartSpec, SheetSpec, nest


def rectangle(width: float, height: float) -> Polygon:
    return Polygon([(0, 0), (width, 0), (width, height), (0, height), (0, 0)])


def test_fill_sheet():
    parts = [PartSpec(part_id="panel", filename="panel.dxf", polygon=rectangle(10, 10), quantity=1)]
    sheets = [SheetSpec(sheet_id="sheet-1", width=20, height=20, quantity=1)]
    
    result = nest(parts, sheets, {
        "mode": "fill_sheet", 
        "gap": 0.0, 
        "rotation": [0], 
        "objective": "maximize_yield"
    })
    
    print(f"Mode: {result['mode']}")
    print(f"Parts placed: {result['parts_placed']}")
    print(f"Used area: {result['used_area']}")
    print(f"Yield: {result['yield']}")
    print(f"Warnings: {result['warnings']}")
    print(f"Summary: {result['summary']}")
    print(f"Parts: {result['parts']}")
    
    assert result["parts_placed"] == 4, f"Expected 4 parts, got {result['parts_placed']}"
    print("✓ Test passed!")


if __name__ == "__main__":
    test_fill_sheet()
