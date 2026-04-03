from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.db import Base, get_engine, init_db, reset_db_state
from app.main import create_app
from app.queue import get_redis
from app.settings import get_settings


@pytest.fixture()
def fake_redis():
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture()
def app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_redis):
    database_path = tmp_path / "test.db"
    storage_dir = tmp_path / "storage"

    monkeypatch.setenv("NESTING_DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("NESTING_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("NESTING_STARTUP_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("NESTING_QUEUE_BLOCK_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    reset_db_state()

    import app.queue as queue_module
    import app.worker as worker_module

    monkeypatch.setattr(queue_module, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(worker_module, "get_redis", lambda: fake_redis)

    settings = get_settings()
    init_db()
    yield settings

    Base.metadata.drop_all(bind=get_engine())
    get_settings.cache_clear()
    reset_db_state()


@pytest.fixture()
def client(app_env):
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def sample_job_payload():
    return {
        "mode": "batch_quantity",
        "parts": [
            {
                "part_id": "part-a",
                "filename": "part-a.dxf",
                "quantity": 2,
                "enabled": True,
                "fill_only": False,
                "order_id": "order-a",
                "order_name": "Order A",
                "priority": 2,
                "polygon": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 40, "y": 0},
                        {"x": 40, "y": 20},
                        {"x": 0, "y": 20},
                        {"x": 0, "y": 0},
                    ]
                },
            }
        ],
        "sheet": {"sheet_id": "sheet-1", "width": 100, "height": 100, "quantity": 1, "units": "mm"},
        "material": {
            "name": "Steel",
            "thickness": 3,
            "sheet_width": 100,
            "sheet_height": 100,
            "units": "mm",
            "kerf": 2,
            "cost_per_sheet": 25,
            "currency": "USD",
            "notes": "Test material",
        },
        "batch": {
            "batch_id": "batch-alpha",
            "batch_name": "Batch Alpha",
            "orders": [{"order_id": "order-a", "order_name": "Order A", "priority": 2, "part_ids": ["part-a"]}],
        },
        "params": {"gap": 2.0, "rotation": [0, 180], "objective": "maximize_yield"},
    }
