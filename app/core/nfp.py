"""
app/core/nfp.py — No-Fit Polygon utilities for nesting placement.

NFP(A, B) is the set of reference-point positions for orbiting polygon B
that cause B to overlap stationary polygon A. Valid placement positions
lie OUTSIDE all NFPs, intersected with the Inner Fit Rectangle (IFR).

Optimal tight-packing positions are always on the boundary of an NFP or
the IFR, so sampling those boundaries gives geometrically superior
candidates compared to a uniform grid scan.

Public API
----------
NFPCache                      — LRU cache for NFP polygons
inner_fit_rectangle(pw, ph, sw, sh)   -> Polygon | None
compute_nfp(stationary, orbiting)     -> Polygon
get_nfp_touch_positions(...)          -> list[(x, y)]
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from shapely.geometry import LinearRing, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class NFPCache:
    """LRU cache for NFP polygons keyed by (stationary_id, orbiting_id)."""

    def __init__(self, max_size: int = 2048) -> None:
        self._store: dict[tuple, Polygon] = {}
        self._max = max_size

    def get(self, key: tuple) -> Polygon | None:
        return self._store.get(key)

    def put(self, key: tuple, nfp: Polygon) -> None:
        if len(self._store) >= self._max:
            # Evict oldest entry (insertion-order dict in Python 3.7+)
            del self._store[next(iter(self._store))]
        self._store[key] = nfp

    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Inner Fit Rectangle
# ---------------------------------------------------------------------------

def inner_fit_rectangle(
    part_w: float,
    part_h: float,
    sheet_w: float,
    sheet_h: float,
) -> Polygon | None:
    """
    Rectangle of valid reference-point positions so the part stays inside
    the sheet.  Returns None if the part is larger than the sheet.
    """
    rw = sheet_w - part_w
    rh = sheet_h - part_h
    if rw < -1e-9 or rh < -1e-9:
        return None
    return box(0.0, 0.0, max(rw, 0.0), max(rh, 0.0))


# ---------------------------------------------------------------------------
# No-Fit Polygon via Minkowski sum
# ---------------------------------------------------------------------------

def compute_nfp(stationary: Polygon, orbiting: Polygon) -> Polygon:
    """
    NFP of *orbiting* around *stationary*.

    Returns the set of positions for orbiting's reference point (0, 0) that
    cause it to overlap stationary.

    Uses convex-hull Minkowski sum: exact for convex shapes, conservative
    (over-estimates forbidden zone) for non-convex shapes.
    """
    try:
        o_pts = list(orbiting.exterior.coords[:-1])
        mirrored_pts = [(-x, -y) for x, y in o_pts]
        mirrored = Polygon(mirrored_pts)
        if not mirrored.is_valid:
            mirrored = mirrored.buffer(0)

        s_hull = stationary.convex_hull
        m_hull = mirrored.convex_hull

        result = _minkowski_sum_convex(s_hull, m_hull)
        return result if result.is_valid else _fallback_nfp(stationary, orbiting)
    except Exception:
        return _fallback_nfp(stationary, orbiting)


def _fallback_nfp(stationary: Polygon, orbiting: Polygon) -> Polygon:
    """Conservative bounding-box NFP used when Minkowski sum fails."""
    sx1, sy1, sx2, sy2 = stationary.bounds
    ox1, oy1, ox2, oy2 = orbiting.bounds
    ow, oh = ox2 - ox1, oy2 - oy1
    return box(sx1 - ow, sy1 - oh, sx2, sy2)


def _minkowski_sum_convex(a: Polygon, b: Polygon) -> Polygon:
    """
    Minkowski sum of two convex polygons.

    Uses the O(m + n) rotating-edge algorithm: merge edge vectors sorted by
    polar angle.  Both polygons must be convex and in CCW orientation.
    """
    a_pts = _ensure_ccw(a)
    b_pts = _ensure_ccw(b)
    n, m = len(a_pts), len(b_pts)

    if n < 3 or m < 3:
        return _bbox_sum(a, b)

    # Find bottom-most (then left-most) starting vertex for each polygon
    ia = min(range(n), key=lambda i: (a_pts[i][1], a_pts[i][0]))
    ib = min(range(m), key=lambda i: (b_pts[i][1], b_pts[i][0]))

    result: list[tuple[float, float]] = [
        (a_pts[ia][0] + b_pts[ib][0], a_pts[ia][1] + b_pts[ib][1])
    ]

    i = j = 0
    while i < n or j < m:
        ai = (ia + i) % n
        aj = (ia + i + 1) % n
        bi = (ib + j) % m
        bj = (ib + j + 1) % m

        ex_a = (a_pts[aj][0] - a_pts[ai][0], a_pts[aj][1] - a_pts[ai][1])
        ex_b = (b_pts[bj][0] - b_pts[bi][0], b_pts[bj][1] - b_pts[bi][1])

        cross = ex_a[0] * ex_b[1] - ex_a[1] * ex_b[0]
        px, py = result[-1]

        if i >= n:
            result.append((px + ex_b[0], py + ex_b[1]))
            j += 1
        elif j >= m:
            result.append((px + ex_a[0], py + ex_a[1]))
            i += 1
        elif cross > 1e-12:
            # edge A comes first (CCW before B)
            result.append((px + ex_a[0], py + ex_a[1]))
            i += 1
        elif cross < -1e-12:
            result.append((px + ex_b[0], py + ex_b[1]))
            j += 1
        else:
            # Parallel edges — advance both
            result.append((px + ex_a[0] + ex_b[0], py + ex_a[1] + ex_b[1]))
            i += 1
            j += 1

    # Remove the closing duplicate
    if len(result) > 1 and _pt_close(result[0], result[-1]):
        result.pop()

    try:
        poly = Polygon(result)
        return poly if poly.is_valid else poly.buffer(0)
    except Exception:
        return _bbox_sum(a, b)


def _ensure_ccw(poly: Polygon) -> list[tuple[float, float]]:
    coords = list(poly.exterior.coords[:-1])
    return coords if LinearRing(coords).is_ccw else list(reversed(coords))


def _bbox_sum(a: Polygon, b: Polygon) -> Polygon:
    ax1, ay1, ax2, ay2 = a.bounds
    bx1, by1, bx2, by2 = b.bounds
    return box(ax1 + bx1, ay1 + by1, ax2 + bx2, ay2 + by2)


def _pt_close(p: tuple[float, float], q: tuple[float, float], eps: float = 1e-9) -> bool:
    return abs(p[0] - q[0]) < eps and abs(p[1] - q[1]) < eps


# ---------------------------------------------------------------------------
# Touch-point position sampling
# ---------------------------------------------------------------------------

def get_nfp_touch_positions(
    part_poly: Polygon,
    part_poly_key: tuple,
    part_w: float,
    part_h: float,
    sheet_w: float,
    sheet_h: float,
    occupied_items: list[tuple[Polygon, tuple, float, float]],
    nfp_cache: NFPCache | None = None,
    max_positions: int = 100,
) -> list[tuple[float, float]]:
    """
    Compute candidate positions where *part_poly* would touch (not overlap)
    each occupied polygon, constrained to remain inside the sheet.

    The optimal tight-packing position is always on such a boundary,
    complementing the grid-based anchor scan.

    Parameters
    ----------
    part_poly      : canonical polygon of new part at this rotation (ref at 0,0)
    part_poly_key  : hashable key for part_poly (e.g. rounded coords tuple)
    part_w / part_h: bounding-box dimensions
    sheet_w / sheet_h: sheet dimensions
    occupied_items : list of (canonical_poly, canonical_key, tx, ty) where tx/ty
                     is the translation applied to canonical_poly to get the placed
                     polygon.  NFP is computed in canonical coords and translated.
    nfp_cache      : optional cache — keyed by (canonical_occ_key, part_poly_key)
    max_positions  : upper bound on returned positions
    """
    ifr = inner_fit_rectangle(part_w, part_h, sheet_w, sheet_h)
    if ifr is None:
        return []

    positions: list[tuple[float, float]] = []
    per_occ = max(4, max_positions // max(len(occupied_items), 1))

    for cano_poly, cano_key, tx, ty in occupied_items:
        cache_key = (cano_key, part_poly_key)
        nfp_canonical: Polygon | None = nfp_cache.get(cache_key) if nfp_cache else None
        if nfp_canonical is None:
            nfp_canonical = compute_nfp(cano_poly, part_poly)
            if nfp_cache is not None:
                nfp_cache.put(cache_key, nfp_canonical)

        if nfp_canonical is None or nfp_canonical.is_empty:
            continue

        # Translate canonical NFP to actual sheet position
        try:
            from shapely import affinity as _aff
            nfp = _aff.translate(nfp_canonical, tx, ty)
            touch_geom = nfp.boundary.intersection(ifr)
            positions.extend(_sample_geom_points(touch_geom, per_occ))
        except Exception:
            pass

    return positions[:max_positions]


def _sample_geom_points(
    geom: BaseGeometry,
    max_pts: int,
) -> list[tuple[float, float]]:
    """Sample up to *max_pts* points from a geometry (line, polygon, or multi)."""
    if geom is None or geom.is_empty:
        return []

    if geom.geom_type in ("MultiLineString", "GeometryCollection", "MultiPolygon"):
        pts: list[tuple[float, float]] = []
        geoms = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        per_sub = max(2, max_pts // max(len(geoms), 1))
        for sub in geoms:
            pts.extend(_sample_geom_points(sub, per_sub))
        return pts[:max_pts]

    if geom.geom_type == "Point":
        return [(geom.x, geom.y)]

    # LineString or Polygon boundary
    coords: list[tuple[float, float]]
    if geom.geom_type == "Polygon":
        coords = list(geom.exterior.coords)
    else:
        coords = list(geom.coords)

    if not coords:
        return []

    total_len = geom.length
    if total_len < 1e-9 or max_pts <= 0:
        return [(coords[0][0], coords[0][1])]

    # Always include vertices (corners are optimal packing positions)
    pts = [(float(x), float(y)) for x, y in coords[:-1]]

    # Also sample intermediate points if we need more
    if len(pts) < max_pts:
        step = total_len / (max_pts - len(pts) + 1)
        d = step
        while d < total_len and len(pts) < max_pts:
            pt = geom.interpolate(d)
            pts.append((pt.x, pt.y))
            d += step

    return pts[:max_pts]
