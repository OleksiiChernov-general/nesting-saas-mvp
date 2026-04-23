from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon


@dataclass(frozen=True)
class CachedRotationEnvelope:
    points: tuple[tuple[float, float], ...]
    width: float
    height: float
    min_x: float
    min_y: float
    polygon: Polygon | None


@dataclass(frozen=True)
class CachedTranslatedGeometry:
    points: tuple[tuple[float, float], ...]
    polygon: Polygon


class PartPlacementCache:
    def __init__(self) -> None:
        self._part_signatures: dict[int, tuple[Any, ...]] = {}
        self._rotation_envelopes: dict[tuple[Any, ...], CachedRotationEnvelope] = {}
        self._translated_geometry: dict[tuple[Any, ...], CachedTranslatedGeometry] = {}
        self._stats = {
            "rotation_envelope_hits": 0,
            "rotation_envelope_misses": 0,
            "translated_geometry_hits": 0,
            "translated_geometry_misses": 0,
        }

    def get_rotation_envelope(
        self,
        part: Any,
        rotation: int,
        factory: Any,
    ) -> CachedRotationEnvelope:
        key = (self._part_signature(part), rotation % 360)
        cached = self._rotation_envelopes.get(key)
        if cached is not None:
            self._stats["rotation_envelope_hits"] += 1
            return cached
        envelope = factory()
        self._rotation_envelopes[key] = envelope
        self._stats["rotation_envelope_misses"] += 1
        return envelope

    def get_translated_geometry(
        self,
        part: Any,
        x: float,
        y: float,
        rotation: int,
        factory: Any,
    ) -> CachedTranslatedGeometry:
        key = (self._part_signature(part), round(x, 6), round(y, 6), rotation % 360)
        cached = self._translated_geometry.get(key)
        if cached is not None:
            self._stats["translated_geometry_hits"] += 1
            return cached
        translated = factory()
        self._translated_geometry[key] = translated
        self._stats["translated_geometry_misses"] += 1
        return translated

    def stats_snapshot(self) -> dict[str, float | int]:
        rotation_requests = self._stats["rotation_envelope_hits"] + self._stats["rotation_envelope_misses"]
        translated_requests = self._stats["translated_geometry_hits"] + self._stats["translated_geometry_misses"]
        return {
            **self._stats,
            "rotation_envelope_hit_rate": round(
                self._stats["rotation_envelope_hits"] / rotation_requests,
                6,
            )
            if rotation_requests
            else 0.0,
            "translated_geometry_hit_rate": round(
                self._stats["translated_geometry_hits"] / translated_requests,
                6,
            )
            if translated_requests
            else 0.0,
        }

    def _part_signature(self, part: Any) -> tuple[Any, ...]:
        cache_key = id(part)
        cached = self._part_signatures.get(cache_key)
        if cached is not None:
            return cached
        signature = _part_signature(part)
        self._part_signatures[cache_key] = signature
        return signature


@dataclass(frozen=True)
class IndexedPlacement:
    index: int
    bounds: Any
    polygon: Polygon


class OccupiedBoundsIndex:
    def __init__(self) -> None:
        self._placements: list[IndexedPlacement] = []
        self._min_x_keys: list[float] = []

    def add(
        self,
        *,
        index: int,
        bounds: Any,
        polygon: Polygon,
    ) -> None:
        placement = IndexedPlacement(index=index, bounds=bounds, polygon=polygon)
        insert_at = bisect_left(self._min_x_keys, float(bounds.min_x))
        self._min_x_keys.insert(insert_at, float(bounds.min_x))
        self._placements.insert(insert_at, placement)

    def find_overlaps(self, candidate_bounds: Any) -> list[IndexedPlacement]:
        cutoff = bisect_left(self._min_x_keys, float(candidate_bounds.max_x))
        overlaps: list[IndexedPlacement] = []
        for placement in self._placements[:cutoff]:
            bounds = placement.bounds
            if float(bounds.max_x) <= float(candidate_bounds.min_x):
                continue
            if float(bounds.max_y) <= float(candidate_bounds.min_y):
                continue
            if float(bounds.min_y) >= float(candidate_bounds.max_y):
                continue
            overlaps.append(placement)
        return overlaps


def _part_signature(part: Any) -> tuple[Any, ...]:
    polygon = tuple((round(float(x), 6), round(float(y), 6)) for x, y in part.polygon)
    bounds = (
        round(float(part.bounds.min_x), 6),
        round(float(part.bounds.min_y), 6),
        round(float(part.bounds.max_x), 6),
        round(float(part.bounds.max_y), 6),
    )
    return (
        str(part.part_id),
        polygon,
        bounds,
        round(float(part.area), 6),
    )
