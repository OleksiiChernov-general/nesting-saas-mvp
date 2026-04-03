from __future__ import annotations

import json

from app.materials import create_material, list_materials, update_material
from app.schemas import MaterialInput
from app.storage import materials_store_path


def test_list_materials_seeds_default_presets(app_env) -> None:
    materials = list_materials()

    assert len(materials) >= 2
    assert all(item.material_id for item in materials)
    assert {item.name for item in materials} >= {"Mild Steel 3 mm", "Stainless 2 mm"}
    assert materials_store_path().exists()


def test_create_material_persists_custom_material(app_env) -> None:
    created = create_material(
        MaterialInput(
            name="Custom Aluminum",
            thickness=1.5,
            sheet_width=2000,
            sheet_height=1000,
            units="mm",
            kerf=1.2,
            cost_per_sheet=40,
            currency="USD",
            notes="Created in a unit test.",
        )
    )

    payload = json.loads(materials_store_path().read_text(encoding="utf-8"))
    stored = next(item for item in payload if item["material_id"] == created.material_id)

    assert created.material_id.startswith("material-")
    assert created.name == "Custom Aluminum"
    assert stored["cost_per_sheet"] == 40.0
    assert stored["currency"] == "USD"


def test_update_material_preserves_created_at_and_writes_changes(app_env) -> None:
    created = create_material(
        MaterialInput(
            name="Custom Steel",
            thickness=3.0,
            sheet_width=3000,
            sheet_height=1500,
            units="mm",
            kerf=2.0,
            notes="Original",
        )
    )

    updated = update_material(
        created.material_id,
        MaterialInput(
            material_id=created.material_id,
            name="Custom Steel Revised",
            thickness=4.0,
            sheet_width=3050,
            sheet_height=1525,
            units="mm",
            kerf=2.5,
            notes="Updated",
        ),
    )

    assert updated is not None
    assert updated.material_id == created.material_id
    assert updated.created_at == created.created_at
    assert updated.updated_at != created.updated_at
    assert updated.sheet_width == 3050
    assert updated.notes == "Updated"


def test_list_materials_recovers_from_invalid_store_payload(app_env) -> None:
    path = materials_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"broken": true}', encoding="utf-8")

    materials = list_materials()

    assert len(materials) >= 2
    restored_payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(restored_payload, list)
    assert restored_payload[0]["material_id"]
