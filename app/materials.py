from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final
from uuid import uuid4

from app.schemas import MaterialInput, MaterialRecord
from app.storage import materials_store_path


DEFAULT_MATERIALS: Final[list[dict[str, object]]] = [
    {
        "material_id": "preset-mild-steel-3mm",
        "name": "Mild Steel 3 mm",
        "thickness": 3.0,
        "sheet_width": 3000.0,
        "sheet_height": 1500.0,
        "units": "mm",
        "kerf": 2.0,
        "cost_per_sheet": None,
        "currency": None,
        "notes": "Default production steel preset.",
    },
    {
        "material_id": "preset-stainless-2mm",
        "name": "Stainless 2 mm",
        "thickness": 2.0,
        "sheet_width": 2500.0,
        "sheet_height": 1250.0,
        "units": "mm",
        "kerf": 1.5,
        "cost_per_sheet": None,
        "currency": None,
        "notes": "Stable starter preset for thinner sheets.",
    },
]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _next_timestamp(previous: str | None = None) -> str:
    current = _utcnow_iso()
    if not previous:
        return current
    try:
        previous_dt = datetime.fromisoformat(previous)
        current_dt = datetime.fromisoformat(current)
    except ValueError:
        return current
    if current_dt <= previous_dt:
        return (previous_dt + timedelta(microseconds=1)).isoformat()
    return current


def _normalize_record(raw: object) -> MaterialRecord | None:
    if not isinstance(raw, dict):
        return None
    try:
        return MaterialRecord.model_validate(raw)
    except Exception:
        return None


def _seed_materials() -> list[MaterialRecord]:
    timestamp = _utcnow_iso()
    return [
        MaterialRecord.model_validate(
            {
                **item,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        for item in DEFAULT_MATERIALS
    ]


def _read_materials(path: Path) -> list[MaterialRecord]:
    if not path.exists():
        materials = _seed_materials()
        _write_materials(path, materials)
        return materials
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        materials = _seed_materials()
        _write_materials(path, materials)
        return materials
    items = payload if isinstance(payload, list) else []
    materials = [record for item in items if (record := _normalize_record(item)) is not None]
    if not materials:
        materials = _seed_materials()
        _write_materials(path, materials)
    return materials


def _write_materials(path: Path, materials: list[MaterialRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([item.model_dump(mode="json") for item in materials], indent=2),
        encoding="utf-8",
    )


def list_materials() -> list[MaterialRecord]:
    return _read_materials(materials_store_path())


def create_material(material: MaterialInput) -> MaterialRecord:
    path = materials_store_path()
    materials = _read_materials(path)
    timestamp = _next_timestamp()
    record = MaterialRecord(
        material_id=material.material_id or f"material-{uuid4()}",
        name=material.name,
        thickness=material.thickness,
        sheet_width=material.sheet_width,
        sheet_height=material.sheet_height,
        units=material.units,
        kerf=material.kerf,
        cost_per_sheet=material.cost_per_sheet,
        currency=material.currency,
        notes=material.notes,
        created_at=timestamp,
        updated_at=timestamp,
    )
    materials.append(record)
    _write_materials(path, materials)
    return record


def update_material(material_id: str, material: MaterialInput) -> MaterialRecord | None:
    path = materials_store_path()
    materials = _read_materials(path)
    for index, existing in enumerate(materials):
        if existing.material_id != material_id:
            continue
        updated = MaterialRecord(
            material_id=material_id,
            name=material.name,
            thickness=material.thickness,
            sheet_width=material.sheet_width,
            sheet_height=material.sheet_height,
            units=material.units,
            kerf=material.kerf,
            cost_per_sheet=material.cost_per_sheet,
            currency=material.currency,
            notes=material.notes,
            created_at=existing.created_at,
            updated_at=_next_timestamp(existing.updated_at),
        )
        materials[index] = updated
        _write_materials(path, materials)
        return updated
    return None
