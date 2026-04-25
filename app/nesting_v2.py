from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import time
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon

from app.nesting_v2_cache import (
    CachedRotationEnvelope,
    CachedTranslatedGeometry,
    OccupiedBoundsIndex,
    PartPlacementCache,
)
from app.core.nfp import NFPCache, get_nfp_touch_positions


DEFAULT_TIME_LIMIT_SEC = 5.0
DEFAULT_ITERATION_CAP = 200_000
CANDIDATE_CAP_BASE = 200
CANDIDATE_CAP_PER_PART = 4
DEFAULT_CANDIDATE_CAP = CANDIDATE_CAP_BASE  # backward-compat alias used by v3
DEFAULT_GRID_STEP = 10.0
DEFAULT_REFILL_PASS_CAP = 8
DEFAULT_ANCHOR_PROBE_MULTIPLIER = 4
IRREGULAR_ROTATIONS = (0, 90, 180, 270)
HEX_OFFSET_RATIO = 0.8660254037844386
GEOMETRY_EPSILON = 1e-6


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def to_dict(self) -> dict[str, float]:
        return {
            "min_x": self.min_x,
            "min_y": self.min_y,
            "max_x": self.max_x,
            "max_y": self.max_y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class NormalizedPart:
    part_id: str
    polygon: list[tuple[float, float]]
    quantity: int
    filename: str | None
    enabled: bool
    fill_only: bool
    order_id: str | None
    order_name: str | None
    priority: int | None
    area: float
    bounds: Bounds
    shape_efficiency: float
    is_axis_aligned_rectangle: bool
    is_triangle: bool
    is_round: bool


@dataclass(frozen=True)
class NormalizedSheet:
    sheet_id: str
    width: float
    height: float
    quantity: int
    units: str

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class EngineLimits:
    time_limit_sec: float
    iteration_cap: int
    candidate_cap: int
    grid_step: float


@dataclass(frozen=True)
class PlacementCandidate:
    x: float
    y: float
    rotation: int


@dataclass(frozen=True)
class CandidateAnchor:
    x: float
    y: float
    source_priority: int


@dataclass(frozen=True)
class OccupiedPlacement:
    bounds: Bounds
    polygon_points: tuple[tuple[float, float], ...]
    polygon: Polygon


@dataclass
class _ProfileFrame:
    label: str
    started_at: float
    child_time_sec: float = 0.0


class _ProfileRecorder:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store
        self._stack: list[_ProfileFrame] = []

    @contextmanager
    def section(self, label: str):
        frame = _ProfileFrame(label=label, started_at=time.perf_counter())
        self._stack.append(frame)
        try:
            yield
        finally:
            finished_at = time.perf_counter()
            completed = self._stack.pop()
            elapsed_sec = finished_at - completed.started_at
            exclusive_sec = max(elapsed_sec - completed.child_time_sec, 0.0)
            section_data = self._store.setdefault(label, {"elapsed_sec": 0.0, "exclusive_sec": 0.0, "calls": 0})
            section_data["elapsed_sec"] += elapsed_sec
            section_data["exclusive_sec"] += exclusive_sec
            section_data["calls"] += 1
            if self._stack:
                self._stack[-1].child_time_sec += elapsed_sec


@contextmanager
def _null_section():
    yield


def _profiled(profiler: _ProfileRecorder | None, label: str, callback: Any) -> Any:
    if profiler is None:
        return callback()
    with profiler.section(label):
        return callback()


def _compute_adaptive_grid_step(parts_raw: list[Any]) -> float:
    from math import gcd
    dims: list[int] = []
    for p in parts_raw:
        pd = p if isinstance(p, dict) else _coerce_mapping(p)
        poly_val = pd.get("polygon") or {}
        if hasattr(poly_val, "exterior"):
            minx, miny, maxx, maxy = poly_val.bounds
            w, h = maxx - minx, maxy - miny
        else:
            pts = poly_val.get("points") if isinstance(poly_val, dict) else []
            if not pts:
                continue
            xs = [pt["x"] for pt in pts]
            ys = [pt["y"] for pt in pts]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w > 0:
            dims.append(max(1, round(w)))
        if h > 0:
            dims.append(max(1, round(h)))
    if not dims:
        return DEFAULT_GRID_STEP
    # GCD of all bounding-box dimensions → step divides every part side exactly,
    # preventing fractional-pixel gaps that block tight rectangular packing.
    g = dims[0]
    for d in dims[1:]:
        g = gcd(g, d)
    return float(max(1, min(int(DEFAULT_GRID_STEP), g)))


def run_nesting(parts: list[Any], sheet: Any, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    started_at = time.perf_counter()
    settings = settings or {}
    if "candidate_cap" not in settings:
        _tmp = _normalize_parts(parts)
        n = sum(p.quantity for p in _tmp)
        settings = {**settings, "candidate_cap": min(CANDIDATE_CAP_BASE + n * CANDIDATE_CAP_PER_PART, 500)}
    if "grid_step" not in settings:
        settings = {**settings, "grid_step": _compute_adaptive_grid_step(parts)}
    profile_store = settings.get("profile_sections")
    profiler = _ProfileRecorder(profile_store) if isinstance(profile_store, dict) else None
    limits = _normalize_limits(settings)
    normalized_parts = _normalize_parts(parts)
    normalized_sheet = _normalize_sheet(sheet)

    placements: list[dict[str, Any]] = []
    occupied: list[Bounds] = []
    occupied_shapes: list[OccupiedPlacement] = []
    occupied_index = OccupiedBoundsIndex()
    part_cache = PartPlacementCache()
    if "use_nfp" not in settings:
        has_irregular = any(not p.is_axis_aligned_rectangle for p in normalized_parts)
        settings = {**settings, "use_nfp": has_irregular}
    use_nfp = bool(settings.get("use_nfp", False))
    nfp_cache: NFPCache | None = NFPCache() if use_nfp else None
    iterations = 0
    timed_out = False
    progress_made = True
    sort_strategy = str(settings.get("sort_strategy", "default"))
    remaining = _build_work_queue(normalized_parts, strategy=sort_strategy)
    refill_pass = 0

    while remaining and progress_made and not timed_out and refill_pass < DEFAULT_REFILL_PASS_CAP:
        refill_scope = (
            profiler.section("refill_loop")
            if profiler is not None and refill_pass > 0
            else _null_section()
        )
        with refill_scope:
            progress_made = False
            next_remaining: list[NormalizedPart] = []

            for index, part in enumerate(remaining):
                if _limits_reached(started_at, iterations, limits):
                    timed_out = True
                    next_remaining.append(part)
                    next_remaining.extend(remaining[index + 1 :])
                    break

                candidate = None
                for candidate_option in prepare_candidates(
                    part,
                    normalized_sheet,
                    occupied,
                    limits,
                    refill_pass=refill_pass,
                    part_cache=part_cache,
                    profiler=profiler,
                    occupied_shapes=occupied_shapes if use_nfp else None,
                    nfp_cache=nfp_cache,
                ):
                    iterations += 1
                    if validate_placement(
                        part,
                        candidate_option,
                        normalized_sheet,
                        occupied,
                        occupied_shapes,
                        occupied_index=occupied_index,
                        part_cache=part_cache,
                        profiler=profiler,
                    ):
                        if _limits_reached(started_at, iterations, limits):
                            timed_out = True
                            break
                        candidate = candidate_option
                        break
                    if _limits_reached(started_at, iterations, limits):
                        timed_out = True
                        break

                if candidate is None:
                    next_remaining.append(part)
                    if timed_out:
                        next_remaining.extend(remaining[index + 1 :])
                        break
                    continue

                placement = commit_placement(part, candidate, normalized_sheet, len(placements) + 1, part_cache=part_cache)
                placements.append(placement)
                occupied_bounds = _bounds_from_dict(placement["bounds"])
                occupied.append(occupied_bounds)
                translated_geometry = _translated_geometry(part, candidate, part_cache)
                polygon_points = translated_geometry.points
                occupied_shapes.append(
                    OccupiedPlacement(
                        bounds=occupied_bounds,
                        polygon_points=polygon_points,
                        polygon=translated_geometry.polygon,
                    )
                )
                occupied_index.add(index=len(occupied) - 1, bounds=occupied_bounds, polygon=translated_geometry.polygon)
                progress_made = True

        remaining = _order_remaining_for_pass(next_remaining, refill_pass + 1)
        refill_pass += 1

    elapsed_sec = min(time.perf_counter() - started_at, limits.time_limit_sec)
    requested_parts = sum(part.quantity for part in normalized_parts)
    result_status = "TIMEOUT" if timed_out else "SUCCEEDED"
    limit_reason = _resolve_limit_reason(started_at, iterations, limits, timed_out)
    metrics = _build_metrics(
        placements=placements,
        requested_parts=requested_parts,
        sheet=normalized_sheet,
        elapsed_sec=elapsed_sec,
        iterations=iterations,
        limits=limits,
        timed_out=timed_out,
        limit_reason=limit_reason,
    )

    return {
        "status": result_status,
        "engine": "v2",
        "placements": placements,
        "metrics": metrics,
        "sheet": {
            "sheet_id": normalized_sheet.sheet_id,
            "width": normalized_sheet.width,
            "height": normalized_sheet.height,
            "quantity": normalized_sheet.quantity,
            "units": normalized_sheet.units,
        },
        "timed_out": timed_out,
        "limit_reason": limit_reason,
        "summary": {
            "total_parts": len(normalized_parts),
            "cache_stats": part_cache.stats_snapshot(),
        },
        "parts": [
            {
                "part_id": part.part_id,
                "filename": part.filename,
                "requested_quantity": part.quantity,
                "placed_quantity": sum(1 for placement in placements if placement["part_id"] == part.part_id),
                "remaining_quantity": max(
                    part.quantity - sum(1 for placement in placements if placement["part_id"] == part.part_id),
                    0,
                ),
                "enabled": part.enabled,
                "area_contribution": sum(
                    float(placement["area"]) for placement in placements if placement["part_id"] == part.part_id
                ),
                "order_id": part.order_id,
                "order_name": part.order_name,
                "priority": part.priority,
            }
            for part in normalized_parts
        ],
    }


def prepare_candidates(
    part: NormalizedPart,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
    limits: EngineLimits,
    refill_pass: int = 0,
    part_cache: PartPlacementCache | None = None,
    profiler: _ProfileRecorder | None = None,
    occupied_shapes: list["OccupiedPlacement"] | None = None,
    nfp_cache: NFPCache | None = None,
) -> list[PlacementCandidate]:
    ranked_candidates: dict[tuple[float, float, int], tuple[tuple[float, ...], PlacementCandidate]] = {}
    cache = part_cache or PartPlacementCache()
    occupied_extent_max_x = max((placed.max_x for placed in occupied), default=0.0)
    occupied_extent_max_y = max((placed.max_y for placed in occupied), default=0.0)

    rotation_scope = profiler.section("rotation_handling") if profiler is not None else _null_section()
    with rotation_scope:
        rotations = _rotation_options(part, refill_pass=refill_pass)

    for rotation in rotations:
        rotation_scope = profiler.section("rotation_handling") if profiler is not None else _null_section()
        with rotation_scope:
            envelope = _rotation_envelope(part, rotation, cache)
        if envelope.width > sheet.width or envelope.height > sheet.height:
            continue
        bounds = Bounds(min_x=0.0, min_y=0.0, max_x=envelope.width, max_y=envelope.height)
        anchor_records = _build_candidate_anchor_records(
            part,
            bounds,
            sheet,
            occupied,
            limits,
            cap=limits.candidate_cap,
            refill_pass=refill_pass,
            profiler=profiler,
        )
        for anchor in anchor_records:
            key = (round(anchor.x, 6), round(anchor.y, 6), rotation)
            candidate = PlacementCandidate(x=key[0], y=key[1], rotation=key[2])
            sort_key = _candidate_rank_key(
                part,
                candidate,
                sheet,
                occupied,
                anchor.source_priority,
                refill_pass,
                part_bounds=bounds,
                part_cache=cache,
                occupied_extent_max_x=occupied_extent_max_x,
                occupied_extent_max_y=occupied_extent_max_y,
            )
            existing = ranked_candidates.get(key)
            if existing is None or sort_key < existing[0]:
                ranked_candidates[key] = (sort_key, candidate)

        # NFP touch-point candidates (geometrically optimal positions)
        if occupied_shapes:
            _add_nfp_candidates(
                ranked_candidates=ranked_candidates,
                part=part,
                rotation=rotation,
                envelope=envelope,
                bounds=bounds,
                sheet=sheet,
                occupied=occupied,
                occupied_shapes=occupied_shapes,
                refill_pass=refill_pass,
                cache=cache,
                nfp_cache=nfp_cache,
                cap=limits.candidate_cap,
                occupied_extent_max_x=occupied_extent_max_x,
                occupied_extent_max_y=occupied_extent_max_y,
            )

    ordered = sorted(ranked_candidates.values(), key=lambda item: item[0])
    return [candidate for _, candidate in ordered[: limits.candidate_cap]]


def _poly_canonical_key(pts: tuple[tuple[float, float], ...]) -> tuple:
    """Stable hashable key from polygon points (rounded to 4 dp)."""
    return tuple((round(x, 4), round(y, 4)) for x, y in pts)


def _add_nfp_candidates(
    *,
    ranked_candidates: dict,
    part: "NormalizedPart",
    rotation: int,
    envelope: "CachedRotationEnvelope",
    bounds: "Bounds",
    sheet: "NormalizedSheet",
    occupied: list["Bounds"],
    occupied_shapes: list["OccupiedPlacement"],
    refill_pass: int,
    cache: "PartPlacementCache",
    nfp_cache: "NFPCache | None",
    cap: int,
    occupied_extent_max_x: float,
    occupied_extent_max_y: float,
) -> None:
    """Inject NFP-boundary touch positions into ranked_candidates.

    Skipped for axis-aligned rectangles — the existing AABB anchor sources
    already find all optimal touch positions for rectangles exactly.
    """
    if _is_axis_aligned_rectangle(part):
        return  # AABB anchors handle rectangles; NFP overhead not justified

    try:
        # Canonical polygon for new part at this rotation (reference at 0, 0)
        pts = tuple((x - envelope.min_x, y - envelope.min_y) for x, y in envelope.points)
        new_poly = Polygon(pts)
        if not new_poly.is_valid:
            new_poly = new_poly.buffer(0)
        if new_poly.is_empty:
            return
        new_key = _poly_canonical_key(pts)

        # Build (canonical_poly, canonical_key, tx, ty) list for occupied shapes
        occupied_items = []
        for occ in occupied_shapes:
            if occ.polygon is None:
                continue
            tx, ty = occ.bounds.min_x, occ.bounds.min_y
            cano_pts = tuple((x - tx, y - ty) for x, y in occ.polygon_points)
            cano_key = _poly_canonical_key(cano_pts)
            cano_poly = Polygon(cano_pts)
            if cano_poly.is_valid and not cano_poly.is_empty:
                occupied_items.append((cano_poly, cano_key, tx, ty))

        if not occupied_items:
            return

        # Limit to avoid O(N) overhead as occupied list grows
        _MAX_NFP_OCC = 8
        if len(occupied_items) > _MAX_NFP_OCC:
            occupied_items = occupied_items[-_MAX_NFP_OCC:]

        positions = get_nfp_touch_positions(
            part_poly=new_poly,
            part_poly_key=new_key,
            part_w=envelope.width,
            part_h=envelope.height,
            sheet_w=sheet.width,
            sheet_h=sheet.height,
            occupied_items=occupied_items,
            nfp_cache=nfp_cache,
            max_positions=cap,
        )

        for x, y in positions:
            x, y = round(x, 6), round(y, 6)
            if x < 0 or y < 0 or x + envelope.width > sheet.width + 1e-9 or y + envelope.height > sheet.height + 1e-9:
                continue
            key = (x, y, rotation)
            candidate = PlacementCandidate(x=x, y=y, rotation=rotation)
            sort_key = _candidate_rank_key(
                part, candidate, sheet, occupied,
                0,
                refill_pass,
                part_bounds=bounds,
                part_cache=cache,
                occupied_extent_max_x=occupied_extent_max_x,
                occupied_extent_max_y=occupied_extent_max_y,
            )
            existing = ranked_candidates.get(key)
            if existing is None or sort_key < existing[0]:
                ranked_candidates[key] = (sort_key, candidate)
    except Exception:
        pass  # NFP failures never break placement


def validate_placement(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
    occupied_shapes: list[OccupiedPlacement] | None = None,
    occupied_index: OccupiedBoundsIndex | None = None,
    part_cache: PartPlacementCache | None = None,
    profiler: _ProfileRecorder | None = None,
) -> bool:
    if part.area <= 0:
        return False
    cache = part_cache or PartPlacementCache()
    fit_scope = profiler.section("fit_check") if profiler is not None else _null_section()
    with fit_scope:
        candidate_bounds = _candidate_bounds(part, candidate, cache)
        is_within_bounds = _is_within_sheet_bounds(candidate_bounds, sheet)
    if not is_within_bounds:
        return False
    if occupied_shapes is None:
        overlap_scope = profiler.section("overlap_check") if profiler is not None else _null_section()
        with overlap_scope:
            has_overlap = _has_any_overlap(candidate_bounds, occupied, occupied_index=occupied_index)
        return not has_overlap
    candidate_polygon = None if _is_axis_aligned_rectangle(part) else _candidate_polygon(part, candidate, cache)
    overlap_scope = profiler.section("overlap_check") if profiler is not None else _null_section()
    with overlap_scope:
        has_overlap = _has_any_overlap(
            candidate_bounds,
            occupied,
            candidate_polygon,
            occupied_shapes,
            occupied_index=occupied_index,
        )
    return not has_overlap


def commit_placement(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    sheet: NormalizedSheet,
    instance: int,
    part_cache: PartPlacementCache | None = None,
) -> dict[str, Any]:
    cache = part_cache or PartPlacementCache()
    translated_polygon = _translate_polygon(part, candidate, cache)
    translated_bounds = _candidate_bounds(part, candidate, cache)
    return {
        "part_id": part.part_id,
        "sheet_id": sheet.sheet_id,
        "instance": instance,
        "rotation": candidate.rotation,
        "x": candidate.x,
        "y": candidate.y,
        "polygon": {"points": translated_polygon},
        "bounds": translated_bounds.to_dict(),
        "area": part.area,
        "filename": part.filename,
        "order_id": part.order_id,
        "order_name": part.order_name,
        "priority": part.priority,
    }


def _normalize_limits(settings: dict[str, Any]) -> EngineLimits:
    return EngineLimits(
        time_limit_sec=max(float(settings.get("time_limit_sec", DEFAULT_TIME_LIMIT_SEC)), 0.01),
        iteration_cap=max(int(settings.get("iteration_cap", DEFAULT_ITERATION_CAP)), 1),
        candidate_cap=max(int(settings.get("candidate_cap", DEFAULT_CANDIDATE_CAP)), 1),
        grid_step=max(float(settings.get("grid_step", DEFAULT_GRID_STEP)), 1.0),
    )


def _normalize_parts(parts: list[Any]) -> list[NormalizedPart]:
    normalized: list[NormalizedPart] = []
    for index, part in enumerate(parts):
        part_data = _coerce_mapping(part)
        if part_data.get("enabled", True) is False:
            continue
        polygon_payload = part_data.get("polygon") or {}
        if hasattr(polygon_payload, "exterior"):
            # Shapely Polygon (e.g. from PartSpec.polygon) — extract coords
            pts = list(polygon_payload.exterior.coords)
            points_payload = [{"x": x, "y": y} for x, y in pts]
        elif isinstance(polygon_payload, dict):
            points_payload = polygon_payload.get("points")
        else:
            points_payload = polygon_payload
        points = _normalize_points(points_payload)
        bounds = _bounds_from_points(points)
        area = _polygon_area(points)
        unique_points = _unique_polygon_points_from_points(points)
        is_axis_aligned_rectangle = _points_are_axis_aligned_rectangle(unique_points)
        is_triangle = len(unique_points) == 3
        is_round = len(unique_points) >= 12 and round(bounds.width, 6) == round(bounds.height, 6)
        bounds_area = bounds.width * bounds.height
        shape_efficiency = round(area / bounds_area, 6) if bounds_area > 0 else float("inf")
        quantity = int(part_data.get("quantity") or 1)
        normalized.append(
            NormalizedPart(
                part_id=str(part_data.get("part_id") or f"part-{index + 1}"),
                polygon=points,
                quantity=max(quantity, 1),
                filename=_optional_text(part_data.get("filename")),
                enabled=True,
                fill_only=bool(part_data.get("fill_only", False)),
                order_id=_optional_text(part_data.get("order_id")),
                order_name=_optional_text(part_data.get("order_name")),
                priority=int(part_data["priority"]) if part_data.get("priority") is not None else None,
                area=area,
                bounds=bounds,
                shape_efficiency=shape_efficiency,
                is_axis_aligned_rectangle=is_axis_aligned_rectangle,
                is_triangle=is_triangle,
                is_round=is_round,
            )
        )
    return normalized


def _normalize_sheet(sheet: Any) -> NormalizedSheet:
    sheet_data = _coerce_mapping(sheet)
    return NormalizedSheet(
        sheet_id=str(sheet_data.get("sheet_id") or "sheet-1"),
        width=float(sheet_data["width"]),
        height=float(sheet_data["height"]),
        quantity=max(int(sheet_data.get("quantity", 1)), 1),
        units=str(sheet_data.get("units") or "mm"),
    )


def _build_work_queue(parts: list[NormalizedPart], strategy: str = "default") -> list[NormalizedPart]:
    ordered_parts = _sort_parts_for_pass(parts, refill_pass=0, strategy=strategy)
    queue: list[NormalizedPart] = []
    for part in ordered_parts:
        queue.extend([part] * part.quantity)
    return queue


def _order_remaining_for_pass(parts: list[NormalizedPart], refill_pass: int) -> list[NormalizedPart]:
    return sorted(parts, key=lambda part: _part_sort_key(part, refill_pass=refill_pass))


def _sort_parts_for_pass(
    parts: list[NormalizedPart],
    refill_pass: int,
    strategy: str = "default",
) -> list[NormalizedPart]:
    if strategy == "area_asc":
        return sorted(parts, key=lambda p: (round(p.area, 6), p.part_id))
    if strategy == "area_desc":
        return sorted(parts, key=lambda p: (-round(p.area, 6), p.part_id))
    if strategy == "perimeter_desc":
        return sorted(parts, key=lambda p: (-round((p.bounds.width + p.bounds.height) * 2, 6), p.part_id))
    if strategy == "aspect_desc":
        return sorted(parts, key=lambda p: (
            -round(max(p.bounds.width, p.bounds.height) / max(min(p.bounds.width, p.bounds.height), 1e-9), 6),
            p.part_id,
        ))
    if strategy == "aspect_asc":
        return sorted(parts, key=lambda p: (
            round(max(p.bounds.width, p.bounds.height) / max(min(p.bounds.width, p.bounds.height), 1e-9), 6),
            p.part_id,
        ))
    return sorted(parts, key=lambda part: _part_sort_key(part, refill_pass=refill_pass))


def _rotation_options(part: NormalizedPart, refill_pass: int = 0) -> list[int]:
    if _is_axis_aligned_rectangle(part):
        return [0]
    if _is_round_part(part):
        return [0]
    if _is_triangle_part(part):
        return [0, 180] if refill_pass == 0 else [0, 180, 90, 270]
    if round(part.bounds.width, 6) == round(part.bounds.height, 6) and _shape_efficiency(part) >= 0.7:
        return [0]
    return list(IRREGULAR_ROTATIONS)


def _bounds_for_rotation(part: NormalizedPart, rotation: int, part_cache: PartPlacementCache | None = None) -> Bounds:
    envelope = _rotation_envelope(part, rotation, part_cache or PartPlacementCache())
    return Bounds(min_x=0.0, min_y=0.0, max_x=envelope.width, max_y=envelope.height)


def _build_candidate_anchors(
    part: NormalizedPart,
    part_bounds: Bounds,
    sheet: NormalizedSheet,
    occupied: list[Bounds] | EngineLimits,
    limits: EngineLimits | None = None,
    cap: int | None = None,
) -> list[tuple[float, float]]:
    return [
        (anchor.x, anchor.y)
        for anchor in _build_candidate_anchor_records(part, part_bounds, sheet, occupied, limits, cap)
    ]


def _build_candidate_anchor_records(
    part: NormalizedPart | Bounds,
    part_bounds: Bounds | NormalizedSheet,
    sheet: NormalizedSheet | list[Bounds],
    occupied: list[Bounds] | EngineLimits,
    limits: EngineLimits | None = None,
    cap: int | None = None,
    refill_pass: int = 0,
    profiler: _ProfileRecorder | None = None,
) -> list[CandidateAnchor]:
    normalized_part: NormalizedPart | None
    if isinstance(part, Bounds):
        normalized_part = None
        resolved_part_bounds = part
        resolved_sheet = part_bounds
        resolved_occupied = sheet
        resolved_limits = occupied
    else:
        normalized_part = part
        resolved_part_bounds = part_bounds
        resolved_sheet = sheet
        resolved_occupied = occupied
        resolved_limits = limits

    if not isinstance(resolved_part_bounds, Bounds):
        raise TypeError("part_bounds must be Bounds")
    if not isinstance(resolved_sheet, NormalizedSheet):
        raise TypeError("sheet must be NormalizedSheet")
    if not isinstance(resolved_occupied, list):
        raise TypeError("occupied must be a list of Bounds")
    if not isinstance(resolved_limits, EngineLimits):
        raise TypeError("limits must be EngineLimits")

    part_bounds = resolved_part_bounds
    sheet = resolved_sheet
    occupied = resolved_occupied
    limits = resolved_limits
    max_x = max(sheet.width - part_bounds.width, 0.0)
    max_y = max(sheet.height - part_bounds.height, 0.0)
    anchor_cap = max(1, cap if cap is not None else limits.candidate_cap)
    probe_cap = max(anchor_cap * DEFAULT_ANCHOR_PROBE_MULTIPLIER, 16)
    ranked_anchors: dict[tuple[float, float], tuple[int, float, float]] = {}
    source_members: dict[int, list[tuple[tuple[float, float], tuple[int, float, float]]]] = {}

    anchor_sources = [
        (
            0,
            _profiled(
                profiler,
                "candidate_generation",
                lambda: _generate_corner_anchors(max_x, max_y),
            ),
        ),
        (
            1,
            _profiled(
                profiler,
                "candidate_generation",
                lambda: _generate_edge_anchors(part_bounds, occupied, probe_cap),
            ),
        ),
        (
            2,
            _profiled(
                profiler,
                "candidate_generation",
                lambda: _generate_wall_aligned_anchors(part_bounds, sheet, occupied, probe_cap),
            ),
        ),
        (
            3,
            _profiled(
                profiler,
                "candidate_generation",
                lambda: _generate_corner_pair_anchors(part_bounds, occupied, probe_cap),
            ),
        ),
    ]
    if normalized_part is not None and refill_pass > 0 and occupied:
        anchor_sources.append(
            (
                4,
                _profiled(
                    profiler,
                    "candidate_generation",
                    lambda: _generate_structured_gap_anchors(
                        normalized_part,
                        part_bounds,
                        sheet,
                        occupied,
                        probe_cap,
                        refill_pass,
                    ),
                ),
            )
        )
    if normalized_part is not None:
        anchor_sources.append(
            (
                5,
                _profiled(
                    profiler,
                    "candidate_generation",
                    lambda: _generate_staggered_anchors(
                        normalized_part,
                        part_bounds,
                        sheet,
                        occupied,
                        limits,
                        probe_cap,
                        refill_pass,
                    ),
                ),
            )
        )
    if normalized_part is None or not _is_round_part(normalized_part):
        anchor_sources.append(
            (
                6,
                _profiled(
                    profiler,
                    "candidate_generation",
                    lambda: _generate_grid_anchors(max_x, max_y, limits.grid_step, probe_cap),
                ),
            )
        )
    if refill_pass > 0:
        anchor_sources.append(
            (
                7,
                _profiled(
                    profiler,
                    "candidate_generation",
                    lambda: _generate_offset_anchors(part_bounds, occupied, probe_cap, refill_pass),
                ),
            )
        )

    ordering_scope = profiler.section("anchor_ordering") if profiler is not None else _null_section()
    with ordering_scope:
        for source_priority, anchors in anchor_sources:
            for x_value, y_value in anchors:
                if y_value < 0.0 or y_value > max_y:
                    continue
                clamped_x = round(min(max(x_value, 0.0), max_x), 6)
                clamped_y = round(y_value, 6)
                key = (clamped_x, clamped_y)
                if source_priority >= 6:
                    sort_key = (source_priority, key[0], key[1])
                else:
                    sort_key = (source_priority, key[1], key[0])
                existing = ranked_anchors.get(key)
                if existing is None or sort_key < existing:
                    ranked_anchors[key] = sort_key
                source_members.setdefault(source_priority, []).append((key, sort_key))

        selected: list[CandidateAnchor] = []
        seen: set[tuple[float, float]] = set()

        for source_priority in sorted(source_members):
            source_candidates = sorted(source_members[source_priority], key=lambda item: item[1])
            for key, _ in source_candidates:
                if key in seen:
                    continue
                selected.append(CandidateAnchor(x=key[0], y=key[1], source_priority=source_priority))
                seen.add(key)
                break
            if len(selected) >= anchor_cap:
                return selected[:anchor_cap]

        ordered = sorted(ranked_anchors.items(), key=lambda item: item[1])
        for key, sort_key in ordered:
            if key in seen:
                continue
            selected.append(CandidateAnchor(x=key[0], y=key[1], source_priority=sort_key[0]))
            seen.add(key)
            if len(selected) >= anchor_cap:
                break
        return selected


def _generate_corner_anchors(max_x: float, max_y: float) -> list[tuple[float, float]]:
    return [
        (0.0, 0.0),
        (0.0, max_y),
        (max_x, 0.0),
        (max_x, max_y),
    ]


def _generate_edge_anchors(
    part_bounds: Bounds,
    occupied: list[Bounds],
    cap: int,
) -> list[tuple[float, float]]:
    anchors: list[tuple[float, float]] = []
    for placed in _sorted_occupied_bounds(occupied):
        anchors.extend(
            [
                (placed.max_x, placed.min_y),
                (placed.max_x, placed.max_y - part_bounds.height),
                (placed.min_x - part_bounds.width, placed.min_y),
                (placed.min_x - part_bounds.width, placed.max_y - part_bounds.height),
                (placed.min_x, placed.max_y),
                (placed.max_x - part_bounds.width, placed.max_y),
                (placed.min_x, placed.min_y - part_bounds.height),
                (placed.max_x - part_bounds.width, placed.min_y - part_bounds.height),
                (placed.max_x, placed.max_y),
            ]
        )
        if len(anchors) >= cap:
            break
    return anchors[:cap]


def _generate_wall_aligned_anchors(
    part_bounds: Bounds,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
    cap: int,
) -> list[tuple[float, float]]:
    if not occupied:
        return []

    max_x = max(sheet.width - part_bounds.width, 0.0)
    max_y = max(sheet.height - part_bounds.height, 0.0)
    anchors: list[tuple[float, float]] = []
    for placed in _sorted_occupied_bounds(occupied):
        x_positions = (
            placed.min_x - part_bounds.width,
            placed.min_x,
            placed.max_x - part_bounds.width,
            placed.max_x,
        )
        y_positions = (
            placed.min_y - part_bounds.height,
            placed.min_y,
            placed.max_y - part_bounds.height,
            placed.max_y,
        )
        for x_value in x_positions:
            anchors.append((x_value, 0.0))
            anchors.append((x_value, max_y))
        for y_value in y_positions:
            anchors.append((0.0, y_value))
            anchors.append((max_x, y_value))
        if len(anchors) >= cap:
            break
    return anchors[:cap]


def _generate_corner_pair_anchors(
    part_bounds: Bounds,
    occupied: list[Bounds],
    cap: int,
) -> list[tuple[float, float]]:
    anchors: list[tuple[float, float]] = []
    for placed in _sorted_occupied_bounds(occupied):
        x_positions = (
            placed.min_x - part_bounds.width,
            placed.min_x,
            placed.max_x - part_bounds.width,
            placed.max_x,
        )
        y_positions = (
            placed.min_y - part_bounds.height,
            placed.min_y,
            placed.max_y - part_bounds.height,
            placed.max_y,
        )
        for y_value in y_positions:
            for x_value in x_positions:
                anchors.append((x_value, y_value))
                if len(anchors) >= cap:
                    return anchors
    return anchors


def _generate_grid_anchors(max_x: float, max_y: float, grid_step: float, cap: int) -> list[tuple[float, float]]:
    anchors: list[tuple[float, float]] = []
    step = max(grid_step, 1.0)
    x = 0.0
    while x <= max_x and len(anchors) < cap:
        y = 0.0
        while y <= max_y and len(anchors) < cap:
            anchors.append((round(x, 6), round(y, 6)))
            y += step
        x += step
    return anchors


def _generate_structured_gap_anchors(
    part: NormalizedPart,
    part_bounds: Bounds,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
    cap: int,
    refill_pass: int,
) -> list[tuple[float, float]]:
    if refill_pass <= 0 or not occupied or not _is_irregular_part(part):
        return []

    x_edges = sorted(
        {
            0.0,
            round(sheet.width, 6),
            *[round(bounds.min_x, 6) for bounds in occupied],
            *[round(bounds.max_x, 6) for bounds in occupied],
        }
    )
    y_edges = sorted(
        {
            0.0,
            round(sheet.height, 6),
            *[round(bounds.min_y, 6) for bounds in occupied],
            *[round(bounds.max_y, 6) for bounds in occupied],
        }
    )
    cells: list[tuple[tuple[float, ...], list[tuple[float, float]]]] = []

    for y_index in range(len(y_edges) - 1):
        min_y = y_edges[y_index]
        max_y = y_edges[y_index + 1]
        cell_height = max_y - min_y
        if cell_height + GEOMETRY_EPSILON < part_bounds.height:
            continue
        for x_index in range(len(x_edges) - 1):
            min_x = x_edges[x_index]
            max_x = x_edges[x_index + 1]
            cell_width = max_x - min_x
            if cell_width + GEOMETRY_EPSILON < part_bounds.width:
                continue

            cell_bounds = Bounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)
            if any(_bounds_overlap(cell_bounds, placed) for placed in occupied):
                continue

            anchors = _structured_cell_anchors(cell_bounds, part_bounds, refill_pass)
            if not anchors:
                continue

            cells.append(
                (
                    _structured_cell_rank(cell_bounds, sheet, occupied),
                    anchors,
                )
            )

    ordered_anchors: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for _, anchors in sorted(cells, key=lambda item: item[0]):
        for anchor in anchors:
            key = (round(anchor[0], 6), round(anchor[1], 6))
            if key in seen:
                continue
            ordered_anchors.append(key)
            seen.add(key)
            if len(ordered_anchors) >= cap:
                return ordered_anchors
    return ordered_anchors


def _structured_cell_anchors(
    cell_bounds: Bounds,
    part_bounds: Bounds,
    refill_pass: int,
) -> list[tuple[float, float]]:
    slack_x = max(cell_bounds.width - part_bounds.width, 0.0)
    slack_y = max(cell_bounds.height - part_bounds.height, 0.0)
    anchors = [
        (cell_bounds.min_x, cell_bounds.min_y),
        (cell_bounds.max_x - part_bounds.width, cell_bounds.min_y),
        (cell_bounds.min_x, cell_bounds.max_y - part_bounds.height),
        (cell_bounds.max_x - part_bounds.width, cell_bounds.max_y - part_bounds.height),
    ]
    if refill_pass > 0:
        anchors.extend(
            [
                (cell_bounds.min_x + (slack_x / 2.0), cell_bounds.min_y),
                (cell_bounds.min_x, cell_bounds.min_y + (slack_y / 2.0)),
            ]
        )

    ordered: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for x_value, y_value in anchors:
        key = (round(x_value, 6), round(y_value, 6))
        if key in seen:
            continue
        ordered.append(key)
        seen.add(key)
    return ordered


def _structured_cell_rank(
    cell_bounds: Bounds,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
) -> tuple[float, ...]:
    occupied_contacts = 0
    wall_contacts = 0
    for placed in occupied:
        horizontal_touch = (
            abs(cell_bounds.max_x - placed.min_x) <= GEOMETRY_EPSILON
            or abs(cell_bounds.min_x - placed.max_x) <= GEOMETRY_EPSILON
        ) and _intervals_overlap(cell_bounds.min_y, cell_bounds.max_y, placed.min_y, placed.max_y)
        vertical_touch = (
            abs(cell_bounds.max_y - placed.min_y) <= GEOMETRY_EPSILON
            or abs(cell_bounds.min_y - placed.max_y) <= GEOMETRY_EPSILON
        ) and _intervals_overlap(cell_bounds.min_x, cell_bounds.max_x, placed.min_x, placed.max_x)
        if horizontal_touch:
            occupied_contacts += 1
        if vertical_touch:
            occupied_contacts += 1

    if abs(cell_bounds.min_x) <= GEOMETRY_EPSILON:
        wall_contacts += 1
    if abs(cell_bounds.min_y) <= GEOMETRY_EPSILON:
        wall_contacts += 1
    if abs(cell_bounds.max_x - sheet.width) <= GEOMETRY_EPSILON:
        wall_contacts += 1
    if abs(cell_bounds.max_y - sheet.height) <= GEOMETRY_EPSILON:
        wall_contacts += 1

    return (
        -float(occupied_contacts),
        float(wall_contacts),
        round(cell_bounds.width * cell_bounds.height, 6),
        round(cell_bounds.min_y, 6),
        round(cell_bounds.min_x, 6),
    )


def _generate_staggered_anchors(
    part: NormalizedPart,
    part_bounds: Bounds,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
    limits: EngineLimits,
    cap: int,
    refill_pass: int,
) -> list[tuple[float, float]]:
    if not _is_irregular_part(part):
        return []

    max_x = max(sheet.width - part_bounds.width, 0.0)
    max_y = max(sheet.height - part_bounds.height, 0.0)
    step_x = max(part_bounds.width, limits.grid_step)
    step_y = max(part_bounds.height * HEX_OFFSET_RATIO, limits.grid_step)
    anchors: list[tuple[float, float]] = []
    row_index = 0
    y_value = 0.0

    while y_value <= max_y + GEOMETRY_EPSILON and len(anchors) < cap:
        offset = 0.0 if row_index % 2 == 0 else min(step_x / 2.0, max_x)
        x_value = offset
        while x_value <= max_x + GEOMETRY_EPSILON and len(anchors) < cap:
            anchors.append((round(x_value, 6), round(min(y_value, max_y), 6)))
            x_value += step_x
        row_index += 1
        y_value += step_y

    if refill_pass > 0 and occupied:
        anchors.extend(
            _generate_offset_anchors(
                part_bounds=part_bounds,
                occupied=occupied,
                cap=max(1, cap - len(anchors)),
                refill_pass=refill_pass,
            )
        )
    return anchors[:cap]


def _generate_offset_anchors(
    part_bounds: Bounds,
    occupied: list[Bounds],
    cap: int,
    refill_pass: int,
) -> list[tuple[float, float]]:
    if not occupied:
        return []

    anchors: list[tuple[float, float]] = []
    half_width = part_bounds.width / 2.0
    half_height = part_bounds.height / 2.0
    hex_height = part_bounds.height * HEX_OFFSET_RATIO
    for placed in _sorted_occupied_bounds(occupied):
        anchors.extend(
            [
                (placed.min_x + half_width, placed.min_y + hex_height),
                (placed.min_x - half_width, placed.min_y + hex_height),
                (placed.min_x + half_width, placed.min_y - hex_height),
                (placed.min_x - half_width, placed.min_y - hex_height),
                (placed.min_x + half_width, placed.min_y + half_height),
                (placed.min_x - half_width, placed.min_y + half_height),
            ]
        )
        if refill_pass > 0:
            anchors.extend(
                [
                    (placed.max_x - half_width, placed.max_y - half_height),
                    (placed.max_x - half_width, placed.min_y - half_height),
                    (placed.min_x - half_width, placed.max_y - half_height),
                ]
            )
        if len(anchors) >= cap:
            break
    return anchors[:cap]


def _sorted_occupied_bounds(occupied: list[Bounds]) -> list[Bounds]:
    return sorted(
        occupied,
        key=lambda bounds: (
            round(bounds.min_y, 6),
            round(bounds.min_x, 6),
            round(bounds.max_x, 6),
            round(bounds.max_y, 6),
        ),
    )


def _intervals_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return min(end_a, end_b) > max(start_a, start_b)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise TypeError(f"Unsupported payload type: {type(value)!r}")


def _normalize_points(points_payload: Any) -> list[tuple[float, float]]:
    if not isinstance(points_payload, list):
        raise ValueError("Polygon points are required")
    points: list[tuple[float, float]] = []
    for point in points_payload:
        point_data = _coerce_mapping(point)
        points.append((float(point_data["x"]), float(point_data["y"])))
    if len(points) < 4:
        raise ValueError("Polygon must contain at least four points including closure")
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def _bounds_from_points(points: list[tuple[float, float]]) -> Bounds:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return Bounds(min(xs), min(ys), max(xs), max(ys))


def _bounds_from_dict(payload: dict[str, Any]) -> Bounds:
    return Bounds(
        min_x=float(payload["min_x"]),
        min_y=float(payload["min_y"]),
        max_x=float(payload["max_x"]),
        max_y=float(payload["max_y"]),
    )


def _polygon_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / 2.0


def _bounds_overlap(left: Bounds, right: Bounds) -> bool:
    return not (
        left.max_x <= right.min_x
        or left.min_x >= right.max_x
        or left.max_y <= right.min_y
        or left.min_y >= right.max_y
    )


def _candidate_bounds(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    part_cache: PartPlacementCache | None = None,
) -> Bounds:
    part_bounds = _bounds_for_rotation(part, candidate.rotation, part_cache)
    return Bounds(
        min_x=candidate.x,
        min_y=candidate.y,
        max_x=candidate.x + part_bounds.width,
        max_y=candidate.y + part_bounds.height,
    )


def _is_within_sheet_bounds(bounds: Bounds, sheet: NormalizedSheet) -> bool:
    return (
        bounds.min_x >= 0.0
        and bounds.min_y >= 0.0
        and bounds.max_x <= sheet.width
        and bounds.max_y <= sheet.height
    )


def _has_any_overlap(
    candidate_bounds: Bounds,
    occupied: list[Bounds],
    candidate_polygon: Polygon | None = None,
    occupied_shapes: list[OccupiedPlacement] | None = None,
    occupied_index: OccupiedBoundsIndex | None = None,
) -> bool:
    if occupied_index is not None:
        overlapping_entries = occupied_index.find_overlaps(candidate_bounds)
        if not overlapping_entries:
            return False
        if candidate_polygon is None or occupied_shapes is None:
            return True
        for entry in overlapping_entries:
            if candidate_polygon.intersection(entry.polygon).area > GEOMETRY_EPSILON:
                return True
        return False

    overlapping_indexes: list[int] = []
    for index, placed in enumerate(occupied):
        if not _bounds_overlap(candidate_bounds, placed):
            continue
        if candidate_polygon is None or occupied_shapes is None:
            return True
        overlapping_indexes.append(index)
    if candidate_polygon is None or occupied_shapes is None:
        return False
    for index in overlapping_indexes:
        if candidate_polygon.intersection(occupied_shapes[index].polygon).area > GEOMETRY_EPSILON:
            return True
    return False


def _build_metrics(
    placements: list[dict[str, Any]],
    requested_parts: int,
    sheet: NormalizedSheet,
    elapsed_sec: float,
    iterations: int,
    limits: EngineLimits,
    timed_out: bool,
    limit_reason: str | None,
) -> dict[str, Any]:
    placed_count = len(placements)
    used_area = sum(float(placement["area"]) for placement in placements)
    sheet_area = sheet.area
    yield_ratio = (used_area / sheet_area) if sheet_area else 0.0
    waste_area = max(sheet_area - used_area, 0.0)
    return {
        "requested_parts": requested_parts,
        "placed_parts": placed_count,
        "placed_count": placed_count,
        "unplaced_parts": max(requested_parts - placed_count, 0),
        "used_area": used_area,
        "sheet_area": sheet_area,
        "waste_area": waste_area,
        "yield_ratio": yield_ratio,
        "yield": yield_ratio,
        "elapsed_sec": elapsed_sec,
        "iterations": iterations,
        "time_limit_sec": limits.time_limit_sec,
        "iteration_cap": limits.iteration_cap,
        "candidate_cap": limits.candidate_cap,
        "timed_out": timed_out,
        "limit_reason": limit_reason,
        "hit_iteration_cap": timed_out and limit_reason == "iteration_cap",
        "hit_time_limit": timed_out and limit_reason == "time_limit_sec",
    }


def _limits_reached(started_at: float, iterations: int, limits: EngineLimits) -> bool:
    return iterations >= limits.iteration_cap or (time.perf_counter() - started_at) >= limits.time_limit_sec


def _resolve_limit_reason(
    started_at: float,
    iterations: int,
    limits: EngineLimits,
    timed_out: bool,
) -> str | None:
    if not timed_out:
        return None
    if iterations >= limits.iteration_cap:
        return "iteration_cap"
    if (time.perf_counter() - started_at) >= limits.time_limit_sec:
        return "time_limit_sec"
    return "bounded_stop"


def _translate_polygon(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    part_cache: PartPlacementCache | None = None,
) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in _translated_geometry(part, candidate, part_cache).points]


def _rotate_point_90(point: tuple[float, float], bounds: Bounds) -> tuple[float, float]:
    x, y = point
    relative_x = x - bounds.min_x
    relative_y = y - bounds.min_y
    return (bounds.height - relative_y, relative_x)


def _rotate_point_180(point: tuple[float, float], bounds: Bounds) -> tuple[float, float]:
    x, y = point
    relative_x = x - bounds.min_x
    relative_y = y - bounds.min_y
    return (bounds.width - relative_x, bounds.height - relative_y)


def _rotate_point_270(point: tuple[float, float], bounds: Bounds) -> tuple[float, float]:
    x, y = point
    relative_x = x - bounds.min_x
    relative_y = y - bounds.min_y
    return (relative_y, bounds.width - relative_x)


def _rotated_points(part: NormalizedPart, rotation: int) -> list[tuple[float, float]]:
    normalized_rotation = rotation % 360
    if normalized_rotation == 0:
        return [(x - part.bounds.min_x, y - part.bounds.min_y) for x, y in part.polygon]
    if normalized_rotation == 90:
        return [_rotate_point_90(point, part.bounds) for point in part.polygon]
    if normalized_rotation == 180:
        return [_rotate_point_180(point, part.bounds) for point in part.polygon]
    if normalized_rotation == 270:
        return [_rotate_point_270(point, part.bounds) for point in part.polygon]
    polygon = Polygon(part.polygon)
    rotated = affinity.rotate(polygon, normalized_rotation, origin=(part.bounds.min_x, part.bounds.min_y))
    return [(float(x), float(y)) for x, y in rotated.exterior.coords]


def _rotation_envelope(
    part: NormalizedPart,
    rotation: int,
    part_cache: PartPlacementCache,
) -> CachedRotationEnvelope:
    def _build() -> CachedRotationEnvelope:
        points = tuple(_rotated_points(part, rotation))
        bounds = _bounds_from_points(list(points))
        polygon = None if _is_axis_aligned_rectangle(part) else Polygon(points)
        return CachedRotationEnvelope(
            points=points,
            width=bounds.width,
            height=bounds.height,
            min_x=bounds.min_x,
            min_y=bounds.min_y,
            polygon=polygon,
        )

    return part_cache.get_rotation_envelope(part, rotation, _build)


def _candidate_polygon(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    part_cache: PartPlacementCache | None = None,
) -> Polygon:
    return _translated_geometry(part, candidate, part_cache).polygon


def _translated_geometry(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    part_cache: PartPlacementCache | None = None,
) -> CachedTranslatedGeometry:
    cache = part_cache or PartPlacementCache()

    def _build() -> CachedTranslatedGeometry:
        envelope = _rotation_envelope(part, candidate.rotation, cache)
        points = tuple(
            (float(x - envelope.min_x + candidate.x), float(y - envelope.min_y + candidate.y))
            for x, y in envelope.points
        )
        return CachedTranslatedGeometry(points=points, polygon=Polygon(points))

    return cache.get_translated_geometry(part, candidate.x, candidate.y, candidate.rotation, _build)


def _polygon_points(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    part_cache: PartPlacementCache | None = None,
) -> list[tuple[float, float]]:
    return list(_translated_geometry(part, candidate, part_cache).points)


def _polygon_points_from_placement(placement: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    polygon_payload = _coerce_mapping(placement["polygon"])
    return tuple(_normalize_points(polygon_payload["points"]))


def _candidate_rank_key(
    part: NormalizedPart,
    candidate: PlacementCandidate,
    sheet: NormalizedSheet,
    occupied: list[Bounds],
    source_priority: int,
    refill_pass: int,
    part_bounds: Bounds | None = None,
    part_cache: PartPlacementCache | None = None,
    occupied_extent_max_x: float = 0.0,
    occupied_extent_max_y: float = 0.0,
) -> tuple[float, ...]:
    candidate_bounds = _candidate_bounds_from_part_bounds(
        part_bounds if part_bounds is not None else _bounds_for_rotation(part, candidate.rotation, part_cache),
        candidate,
    )
    contact_score = _contact_score(candidate_bounds, sheet, occupied)
    contact_span = _contact_span(candidate_bounds, sheet, occupied)
    extent_area = _resulting_extent_area(
        candidate_bounds,
        occupied,
        occupied_extent_max_x=occupied_extent_max_x,
        occupied_extent_max_y=occupied_extent_max_y,
    )
    rotation_rank = _rotation_rank(part, candidate.rotation, refill_pass)
    if _is_axis_aligned_rectangle(part):
        return (
            float(refill_pass),
            round(extent_area, 6),
            -round(contact_span, 6),
            -float(contact_score),
            float(source_priority),
            round(candidate_bounds.min_y, 6),
            round(candidate_bounds.min_x, 6),
            float(rotation_rank),
            float(candidate.rotation),
        )
    if _is_round_part(part):
        return (
            float(refill_pass),
            round(extent_area, 6),
            -round(contact_span, 6),
            -float(contact_score),
            round(candidate_bounds.min_y, 6),
            round(candidate_bounds.min_x, 6),
            float(source_priority),
            float(rotation_rank),
            float(candidate.rotation),
            float(_irregular_overlap_penalty(part, candidate_bounds, occupied, candidate.rotation)),
        )
    if refill_pass <= 0:
        return (
            float(refill_pass),
            float(source_priority),
            round(candidate_bounds.min_y, 6),
            round(candidate_bounds.min_x, 6),
            float(rotation_rank),
            float(candidate.rotation),
            float(_irregular_overlap_penalty(part, candidate_bounds, occupied, candidate.rotation)),
            round(extent_area, 6),
            -round(contact_span, 6),
            -float(contact_score),
        )
    return (
        float(refill_pass),
        round(extent_area, 6),
        -round(contact_span, 6),
        -float(contact_score),
        round(candidate_bounds.min_y, 6),
        round(candidate_bounds.min_x, 6),
        float(rotation_rank),
        float(candidate.rotation),
        float(source_priority),
        float(_irregular_overlap_penalty(part, candidate_bounds, occupied, candidate.rotation)),
    )


def _candidate_bounds_from_part_bounds(part_bounds: Bounds, candidate: PlacementCandidate) -> Bounds:
    return Bounds(
        min_x=candidate.x,
        min_y=candidate.y,
        max_x=candidate.x + part_bounds.width,
        max_y=candidate.y + part_bounds.height,
    )


def _contact_score(candidate_bounds: Bounds, sheet: NormalizedSheet, occupied: list[Bounds]) -> int:
    score = 0
    if abs(candidate_bounds.min_x) <= GEOMETRY_EPSILON:
        score += 2
    if abs(candidate_bounds.min_y) <= GEOMETRY_EPSILON:
        score += 2
    if abs(candidate_bounds.max_x - sheet.width) <= GEOMETRY_EPSILON:
        score += 2
    if abs(candidate_bounds.max_y - sheet.height) <= GEOMETRY_EPSILON:
        score += 2
    for placed in occupied:
        horizontal_touch = (
            abs(candidate_bounds.max_x - placed.min_x) <= GEOMETRY_EPSILON
            or abs(candidate_bounds.min_x - placed.max_x) <= GEOMETRY_EPSILON
        ) and _intervals_overlap(candidate_bounds.min_y, candidate_bounds.max_y, placed.min_y, placed.max_y)
        vertical_touch = (
            abs(candidate_bounds.max_y - placed.min_y) <= GEOMETRY_EPSILON
            or abs(candidate_bounds.min_y - placed.max_y) <= GEOMETRY_EPSILON
        ) and _intervals_overlap(candidate_bounds.min_x, candidate_bounds.max_x, placed.min_x, placed.max_x)
        if horizontal_touch:
            score += 1
        if vertical_touch:
            score += 1
    return score


def _contact_span(candidate_bounds: Bounds, sheet: NormalizedSheet, occupied: list[Bounds]) -> float:
    span = 0.0
    if abs(candidate_bounds.min_x) <= GEOMETRY_EPSILON:
        span += candidate_bounds.height
    if abs(candidate_bounds.min_y) <= GEOMETRY_EPSILON:
        span += candidate_bounds.width
    if abs(candidate_bounds.max_x - sheet.width) <= GEOMETRY_EPSILON:
        span += candidate_bounds.height
    if abs(candidate_bounds.max_y - sheet.height) <= GEOMETRY_EPSILON:
        span += candidate_bounds.width
    for placed in occupied:
        if (
            abs(candidate_bounds.max_x - placed.min_x) <= GEOMETRY_EPSILON
            or abs(candidate_bounds.min_x - placed.max_x) <= GEOMETRY_EPSILON
        ):
            span += max(
                min(candidate_bounds.max_y, placed.max_y) - max(candidate_bounds.min_y, placed.min_y),
                0.0,
            )
        if (
            abs(candidate_bounds.max_y - placed.min_y) <= GEOMETRY_EPSILON
            or abs(candidate_bounds.min_y - placed.max_y) <= GEOMETRY_EPSILON
        ):
            span += max(
                min(candidate_bounds.max_x, placed.max_x) - max(candidate_bounds.min_x, placed.min_x),
                0.0,
            )
    return span


def _resulting_extent_area(
    candidate_bounds: Bounds,
    occupied: list[Bounds],
    occupied_extent_max_x: float = 0.0,
    occupied_extent_max_y: float = 0.0,
) -> float:
    max_x = max(candidate_bounds.max_x, occupied_extent_max_x)
    max_y = max(candidate_bounds.max_y, occupied_extent_max_y)
    if occupied_extent_max_x <= 0.0 and occupied_extent_max_y <= 0.0:
        for placed in occupied:
            max_x = max(max_x, placed.max_x)
            max_y = max(max_y, placed.max_y)
    return max_x * max_y


def _irregular_overlap_penalty(
    part: NormalizedPart,
    candidate_bounds: Bounds,
    occupied: list[Bounds],
    rotation: int,
) -> int:
    if not _is_irregular_part(part) or _is_round_part(part):
        return 0
    penalty = 0
    for placed in occupied:
        if not _bounds_overlap(candidate_bounds, placed):
            continue
        if _is_triangle_part(part) and rotation == 180 and _same_size_bounds(candidate_bounds, placed):
            continue
        penalty += 1
    return penalty


def _shape_efficiency(part: NormalizedPart) -> float:
    return part.shape_efficiency


def _is_axis_aligned_rectangle(part: NormalizedPart) -> bool:
    return part.is_axis_aligned_rectangle


def _is_triangle_part(part: NormalizedPart) -> bool:
    return part.is_triangle


def _is_round_part(part: NormalizedPart) -> bool:
    return part.is_round


def _is_irregular_part(part: NormalizedPart) -> bool:
    return not _is_axis_aligned_rectangle(part)


def _unique_polygon_points(part: NormalizedPart) -> list[tuple[float, float]]:
    return _unique_polygon_points_from_points(part.polygon)


def _unique_polygon_points_from_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique_points: list[tuple[float, float]] = []
    for point in points[:-1]:
        if point not in unique_points:
            unique_points.append(point)
    return unique_points


def _points_are_axis_aligned_rectangle(unique_points: list[tuple[float, float]]) -> bool:
    if len(unique_points) != 4:
        return False
    xs = {round(point[0], 6) for point in unique_points}
    ys = {round(point[1], 6) for point in unique_points}
    return len(xs) == 2 and len(ys) == 2


def _same_size_bounds(left: Bounds, right: Bounds) -> bool:
    return (
        abs(left.min_x - right.min_x) <= GEOMETRY_EPSILON
        and abs(left.min_y - right.min_y) <= GEOMETRY_EPSILON
        and abs(left.max_x - right.max_x) <= GEOMETRY_EPSILON
        and abs(left.max_y - right.max_y) <= GEOMETRY_EPSILON
    )


def _rotation_rank(part: NormalizedPart, rotation: int, refill_pass: int) -> int:
    if _is_triangle_part(part):
        preferred = (0, 180, 90, 270) if refill_pass > 0 else (0, 180)
        if rotation in preferred:
            return preferred.index(rotation)
    return 0


def _part_sort_key(part: NormalizedPart, refill_pass: int) -> tuple[float | str, ...]:
    footprint = round(part.bounds.width * part.bounds.height, 6)
    irregular_priority = 0 if _is_irregular_part(part) else 1
    if refill_pass > 0:
        return (
            irregular_priority,
            footprint,
            _shape_efficiency(part),
            -round(part.area, 6),
            part.part_id,
        )
    return (
        irregular_priority,
        _shape_efficiency(part),
        -round(part.area, 6),
        -footprint,
        part.part_id,
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
