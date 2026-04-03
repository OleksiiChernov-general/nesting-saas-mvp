from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.artifacts import artifact_content_type, ensure_artifact
from app.db import get_db
from app.materials import create_material, list_materials, update_material
from app.models import JobState, NestingJob
from app.queue import enqueue_job
from app.schemas import (
    CleanGeometryRequest,
    CleanGeometryResponse,
    ImportResponse,
    JobResponse,
    MaterialInput,
    MaterialRecord,
    NestingJobCreateRequest,
    NestingResultResponse,
)
from app.services import (
    clean_geometry_payload,
    create_job_record,
    get_job_result,
    import_dxf,
    mark_job_queued,
    recover_stale_jobs,
    serialize_job,
)
from app.settings import get_settings
from app.storage import artifact_download_name, result_download_name, save_imported_file


router = APIRouter(prefix="/v1")


@router.get("/materials", response_model=list[MaterialRecord])
def get_materials() -> list[MaterialRecord]:
    return list_materials()


@router.post("/materials", response_model=MaterialRecord, status_code=201)
def create_material_endpoint(request: MaterialInput) -> MaterialRecord:
    return create_material(request)


@router.put("/materials/{material_id}", response_model=MaterialRecord)
def update_material_endpoint(material_id: str, request: MaterialInput) -> MaterialRecord:
    material = update_material(material_id, request)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


@router.post("/files/import", response_model=ImportResponse)
async def import_file(file: UploadFile = File(...)) -> ImportResponse:
    import_id = str(uuid.uuid4())
    file_path = await save_imported_file(file, import_id)
    return import_dxf(str(file_path), file.filename or "upload.dxf", import_id, get_settings().geometry_tolerance)


@router.post("/geometry/clean", response_model=CleanGeometryResponse)
def clean_geometry(request: CleanGeometryRequest) -> CleanGeometryResponse:
    return clean_geometry_payload(request)


@router.post("/nesting/jobs", response_model=JobResponse, status_code=202)
def create_nesting_job(request: NestingJobCreateRequest, db: Session = Depends(get_db)) -> JobResponse:
    recover_stale_jobs()
    job = create_job_record(db, request)
    enqueue_job(job.id)
    job = mark_job_queued(db, job)
    return JobResponse.model_validate(serialize_job(job))


@router.get("/nesting/jobs/{job_id}", response_model=JobResponse)
def get_nesting_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobResponse:
    recover_stale_jobs()
    job = db.get(NestingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(serialize_job(job))


@router.get("/nesting/jobs/{job_id}/result", response_model=NestingResultResponse)
def get_nesting_job_result(job_id: uuid.UUID, db: Session = Depends(get_db)) -> NestingResultResponse:
    recover_stale_jobs()
    job = db.get(NestingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state not in {JobState.SUCCEEDED, JobState.PARTIAL}:
        raise HTTPException(status_code=409, detail=f"Job is {job.state}")
    return NestingResultResponse.model_validate(get_job_result(job))


@router.get("/nesting/jobs/{job_id}/artifact")
def download_nesting_job_artifact(job_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    recover_stale_jobs()
    job = db.get(NestingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        artifact_path = ensure_artifact(job, "json")
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail=f"Artifact is unavailable while job is {job.state}") from None
    return FileResponse(artifact_path, media_type="application/json", filename=result_download_name(job.id))


@router.get("/nesting/jobs/{job_id}/artifact/{artifact_kind}")
def download_named_nesting_job_artifact(
    job_id: uuid.UUID,
    artifact_kind: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    if artifact_kind == "json":
        return download_nesting_job_artifact(job_id, db)

    recover_stale_jobs()
    job = db.get(NestingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if artifact_kind not in {"dxf", "pdf"}:
        raise HTTPException(status_code=404, detail="Artifact kind not found")
    try:
        artifact_path = ensure_artifact(job, artifact_kind)
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail=f"Artifact is unavailable while job is {job.state}") from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(
        artifact_path,
        media_type=artifact_content_type(artifact_kind),
        filename=artifact_download_name(job.id, artifact_kind),
    )
