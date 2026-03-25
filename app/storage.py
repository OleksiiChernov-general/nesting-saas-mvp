from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.settings import get_settings


def ensure_storage() -> None:
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.imports_dir.mkdir(parents=True, exist_ok=True)
    settings.results_dir.mkdir(parents=True, exist_ok=True)


async def save_imported_file(upload: UploadFile, import_id: str) -> Path:
    settings = get_settings()
    ensure_storage()
    target = settings.imports_dir / f"{import_id}_{upload.filename}"
    data = await upload.read()
    target.write_bytes(data)
    return target


def save_job_result(job_id: UUID, payload: dict) -> Path:
    settings = get_settings()
    ensure_storage()
    target = settings.results_dir / f"{job_id}.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def result_download_name(job_id: UUID) -> str:
    return f"nesting-result-{job_id}.json"


def load_job_result(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
