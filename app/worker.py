from __future__ import annotations

import json
import logging
import time
from uuid import UUID

from app.db import get_session_factory, init_db, wait_for_database
from app.models import NestingJob
from app.queue import get_redis, wait_for_redis
from app.services import run_nesting_job
from app.settings import get_settings
from app.storage import ensure_storage


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_next_job(timeout: int | None = None) -> bool:
    settings = get_settings()
    redis_client = get_redis()
    message = redis_client.blpop(
        settings.job_queue_name,
        timeout=settings.queue_block_timeout_seconds if timeout is None else timeout,
    )
    if message is None:
        return False
    _, raw_payload = message
    job_id = UUID(json.loads(raw_payload)["job_id"])
    with get_session_factory()() as db:
        job = db.get(NestingJob, job_id)
        if not job:
            logger.warning("Job %s not found", job_id)
            return False
        try:
            run_nesting_job(db, job)
            logger.info("Job %s succeeded", job_id)
            return True
        except Exception:
            logger.exception("Job %s failed", job_id)
            return True


def main() -> None:
    settings = get_settings()
    ensure_storage()
    wait_for_database(settings.startup_timeout_seconds)
    init_db()
    wait_for_redis(settings.startup_timeout_seconds)
    logger.info("Worker started, queue=%s", settings.job_queue_name)
    while True:
        processed = process_next_job()
        if not processed:
            time.sleep(settings.worker_idle_sleep_seconds)


if __name__ == "__main__":
    main()
