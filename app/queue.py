from __future__ import annotations

import json
import time
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from app.settings import get_settings


def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def wait_for_redis(timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            get_redis().ping()
            return
        except RedisError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Redis is not ready after {timeout_seconds} seconds") from last_error


def enqueue_job(job_id: UUID) -> None:
    payload = json.dumps({"job_id": str(job_id)})
    get_redis().rpush(get_settings().job_queue_name, payload)
