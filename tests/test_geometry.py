from __future__ import annotations

from shapely.geometry import Polygon

from app.geometry import clean_geometry


def test_clean_geometry_deduplicates_equal_polygons():
    polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])

    cleaned, issues = clean_geometry([polygon, polygon], tolerance=0.5)

    assert len(cleaned) == 1
    assert issues == []


def test_clean_geometry_rejects_self_intersection():
    bowtie = Polygon([(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)])

    cleaned, issues = clean_geometry([bowtie], tolerance=0.5)

    assert cleaned == []
    assert issues
