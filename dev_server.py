"""
Self-contained development server.
Uses SQLite (local.db) + fakeredis in-process.
No PostgreSQL or real Redis needed.

Usage:  python dev_server.py
"""
from __future__ import annotations

import os
import sys
import time
import threading
import logging

# ── 1. Env vars BEFORE any app import ──────────────────────────────────────
os.environ.setdefault("NESTING_DATABASE_URL", "sqlite:///./local.db")
os.environ.setdefault("NESTING_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NESTING_ENGINE_BACKEND", "v2")
os.environ.setdefault("NESTING_CORS_ALLOWED_ORIGINS", "*")
os.environ.setdefault("NESTING_STARTUP_TIMEOUT_SECONDS", "5")
os.environ.setdefault("NESTING_MAX_COMPUTE_SECONDS", "60")
os.environ.setdefault("NESTING_NATIVE_POC_ENABLED", "false")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dev_server")

# ── 2. Patch Redis with fakeredis BEFORE app.queue is imported ──────────────
try:
    import fakeredis

    _fake_server = fakeredis.FakeServer()
    _fake_redis  = fakeredis.FakeRedis(server=_fake_server, decode_responses=True)

    import app.queue as _queue_module
    _queue_module.get_redis    = lambda: _fake_redis
    _queue_module.wait_for_redis = lambda *_a, **_kw: None  # skip ping

    # Also patch main.py lifespan's wait_for_redis import
    import app.main as _main_module
    _main_module.wait_for_redis = lambda *_a, **_kw: None  # type: ignore[attr-defined]

    logger.info("Redis → fakeredis (in-memory) ✓")
except ImportError:
    logger.error("fakeredis not installed. Run: pip install fakeredis")
    sys.exit(1)

# ── 3. Init DB + storage ────────────────────────────────────────────────────
from app.db import init_db, wait_for_database
from app.storage import ensure_storage
from app.settings import get_settings
from app.services import recover_stale_jobs

settings = get_settings()
ensure_storage()
logger.info("Waiting for SQLite database…")
wait_for_database(settings.startup_timeout_seconds)
init_db()
recover_stale_jobs()
logger.info("SQLite DB initialised ✓")

# ── 4. Background worker thread ─────────────────────────────────────────────
from app.worker import process_next_job

def _worker_loop() -> None:
    logger.info("Worker thread started ✓")
    while True:
        try:
            process_next_job()
        except Exception:
            logger.exception("Worker iteration error")
        time.sleep(0.1)

_worker = threading.Thread(target=_worker_loop, daemon=True, name="nesting-worker")
_worker.start()

# ── 5. Start uvicorn ─────────────────────────────────────────────────────────
import uvicorn

logger.info("Starting API on http://127.0.0.1:8000")
logger.info("Frontend expected on http://127.0.0.1:5173")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
