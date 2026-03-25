from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.db import init_db, wait_for_database
from app.queue import wait_for_redis
from app.settings import get_settings
from app.storage import ensure_storage


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    ensure_storage()
    wait_for_database(settings.startup_timeout_seconds)
    init_db()
    wait_for_redis(settings.startup_timeout_seconds)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Nesting SaaS MVP", lifespan=lifespan)

    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
