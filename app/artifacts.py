from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from uuid import UUID

import ezdxf

from app.models import JobState, NestingJob
from app.storage import artifact_download_name, artifact_error_path, artifact_store_path, load_job_result


ARTIFACT_CONTENT_TYPES: dict[str, str] = {
    "json": "application/json",
    "dxf": "application/dxf",
    "pdf": "application/pdf",
}


def artifact_url(job_id: UUID, artifact_kind: str) -> str:
    if artifact_kind == "json":
        return f"/v1/nesting/jobs/{job_id}/artifact"
    return f"/v1/nesting/jobs/{job_id}/artifact/{artifact_kind}"


def resolve_artifacts(job: NestingJob, result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [resolve_artifact(job, kind, result=result) for kind in ("json", "dxf", "pdf")]


def resolve_artifact(job: NestingJob, artifact_kind: str, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
    if artifact_kind not in {"json", "dxf", "pdf"}:
        raise ValueError(f"Unsupported artifact kind: {artifact_kind}")

    if artifact_kind == "json":
        return _resolve_json_artifact(job)

    existing_path = artifact_store_path(job.id, artifact_kind)
    error_path = artifact_error_path(job.id, artifact_kind)
    loaded_result = result if result is not None else _load_result(job)
    ready_for_generation = _job_has_finished(job) and loaded_result is not None

    if existing_path.exists():
        return _artifact_descriptor(
            job.id,
            artifact_kind,
            "available",
            f"{artifact_kind.upper()} artifact is ready to download.",
            url=artifact_url(job.id, artifact_kind),
            filename=artifact_download_name(job.id, artifact_kind),
        )

    if error_path.exists():
        return _artifact_descriptor(
            job.id,
            artifact_kind,
            "failed",
            error_path.read_text(encoding="utf-8").strip() or f"{artifact_kind.upper()} export failed.",
        )

    if not ready_for_generation:
        if job.state in {JobState.CREATED, JobState.QUEUED, JobState.RUNNING}:
            return _artifact_descriptor(
                job.id,
                artifact_kind,
                "processing",
                f"{artifact_kind.upper()} export will be available after the nesting job finishes.",
            )
        return _artifact_descriptor(
            job.id,
            artifact_kind,
            "unavailable",
            f"{artifact_kind.upper()} export is unavailable because no completed result exists yet.",
        )

    if artifact_kind == "dxf":
        if not _has_layout_geometry(loaded_result):
            return _artifact_descriptor(
                job.id,
                artifact_kind,
                "unavailable",
                "DXF export is unavailable because the result contains no layout geometry.",
            )
        return _artifact_descriptor(
            job.id,
            artifact_kind,
            "available",
            "DXF export is generated on demand from the current layout result.",
            url=artifact_url(job.id, artifact_kind),
            filename=artifact_download_name(job.id, artifact_kind),
        )

    if artifact_kind == "pdf":
        return _artifact_descriptor(
            job.id,
            artifact_kind,
            "available",
            "PDF report is generated on demand from the current job summary.",
            url=artifact_url(job.id, artifact_kind),
            filename=artifact_download_name(job.id, artifact_kind),
        )

    return _artifact_descriptor(job.id, artifact_kind, "unavailable", "Artifact state is unavailable.")


def ensure_artifact(job: NestingJob, artifact_kind: str) -> Path:
    if artifact_kind == "json":
        path = _json_result_path(job)
        if path is None:
            raise FileNotFoundError("JSON result artifact is unavailable.")
        return path

    result = _load_result(job)
    if result is None:
        raise FileNotFoundError(f"{artifact_kind.upper()} artifact is unavailable because the result is missing.")

    target = artifact_store_path(job.id, artifact_kind)
    error_path = artifact_error_path(job.id, artifact_kind)
    if target.exists():
        return target

    try:
        if artifact_kind == "dxf":
            _write_dxf_artifact(job, result, target)
        elif artifact_kind == "pdf":
            _write_pdf_artifact(job, result, target)
        else:
            raise FileNotFoundError(f"Unsupported artifact kind: {artifact_kind}")
    except Exception as exc:
        error_path.write_text(f"{artifact_kind.upper()} export failed: {exc}", encoding="utf-8")
        raise
    else:
        if error_path.exists():
            error_path.unlink()
    return target


def artifact_content_type(artifact_kind: str) -> str:
    return ARTIFACT_CONTENT_TYPES[artifact_kind]


def _resolve_json_artifact(job: NestingJob) -> dict[str, Any]:
    path = _json_result_path(job)
    if path is not None and path.exists():
        return _artifact_descriptor(
            job.id,
            "json",
            "available",
            "JSON result is ready to download from the current job.",
            url=artifact_url(job.id, "json"),
            filename=artifact_download_name(job.id, "json"),
        )
    if job.state in {JobState.CREATED, JobState.QUEUED, JobState.RUNNING}:
        return _artifact_descriptor(
            job.id,
            "json",
            "processing",
            "JSON result will be available after the nesting job finishes.",
        )
    if _job_has_finished(job):
        return _artifact_descriptor(
            job.id,
            "json",
            "failed",
            "JSON result should exist for a completed job, but the file is missing.",
        )
    return _artifact_descriptor(job.id, "json", "unavailable", "JSON result is unavailable.")


def _artifact_descriptor(
    job_id: UUID,
    artifact_kind: str,
    status: str,
    message: str,
    *,
    url: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    labels = {
        "json": "JSON result",
        "dxf": "DXF layout",
        "pdf": "PDF report",
    }
    return {
        "kind": artifact_kind,
        "label": labels[artifact_kind],
        "status": status,
        "url": url,
        "message": message,
        "content_type": ARTIFACT_CONTENT_TYPES.get(artifact_kind),
        "filename": filename,
    }


def _load_result(job: NestingJob) -> dict[str, Any] | None:
    path = _json_result_path(job)
    if path is None or not path.exists():
        return None
    result = load_job_result(path)
    return result if isinstance(result, dict) else None


def _json_result_path(job: NestingJob) -> Path | None:
    if job.artifact_path:
        return Path(job.artifact_path)
    if job.result_path:
        return Path(job.result_path)
    return None


def _job_has_finished(job: NestingJob) -> bool:
    return job.state in {JobState.SUCCEEDED, JobState.PARTIAL}


def _has_layout_geometry(result: dict[str, Any]) -> bool:
    layouts = result.get("layouts")
    return isinstance(layouts, list) and any(isinstance(layout, dict) for layout in layouts)


def _write_dxf_artifact(job: NestingJob, result: dict[str, Any], target: Path) -> None:
    layouts = result.get("layouts")
    if not isinstance(layouts, list) or not layouts:
        raise ValueError("No layout geometry is available for DXF export.")

    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    units = _detect_units_code(job, result)
    try:
        doc.units = units
    except Exception:
        pass

    x_cursor = 0.0
    spacing = 50.0
    for layout_index, layout in enumerate(layouts, start=1):
        if not isinstance(layout, dict):
            continue
        sheet_width = _to_float(layout.get("width"))
        sheet_height = _to_float(layout.get("height"))
        if sheet_width <= 0 or sheet_height <= 0:
            continue
        outline = [
            (x_cursor, 0.0),
            (x_cursor + sheet_width, 0.0),
            (x_cursor + sheet_width, sheet_height),
            (x_cursor, sheet_height),
            (x_cursor, 0.0),
        ]
        msp.add_lwpolyline(outline, dxfattribs={"layer": "SHEETS", "closed": True})
        msp.add_text(
            f"{layout.get('sheet_id', 'sheet')} #{layout.get('instance', layout_index)}",
            dxfattribs={"layer": "ANNOTATION", "height": max(sheet_height * 0.03, 5.0)},
        ).set_placement((x_cursor, sheet_height + max(sheet_height * 0.05, 10.0)))

        placements = layout.get("placements")
        if isinstance(placements, list):
            for placement_index, placement in enumerate(placements, start=1):
                if not isinstance(placement, dict):
                    continue
                polygon = placement.get("polygon")
                points = _polygon_points(polygon)
                if len(points) < 4:
                    x = _to_float(placement.get("x"))
                    y = _to_float(placement.get("y"))
                    width = _to_float(placement.get("width"))
                    height = _to_float(placement.get("height"))
                    if width <= 0 or height <= 0:
                        continue
                    points = [
                        (x, y),
                        (x + width, y),
                        (x + width, y + height),
                        (x, y + height),
                        (x, y),
                    ]
                shifted = [(x + x_cursor, y) for x, y in points]
                msp.add_lwpolyline(shifted, dxfattribs={"layer": "PLACEMENTS", "closed": True})
                label_x, label_y = shifted[0]
                msp.add_text(
                    str(placement.get("part_id") or f"part-{placement_index}"),
                    dxfattribs={"layer": "ANNOTATION", "height": max(min(sheet_width, sheet_height) * 0.02, 2.5)},
                ).set_placement((label_x, label_y))

        x_cursor += sheet_width + spacing

    doc.saveas(target)


def _write_pdf_artifact(job: NestingJob, result: dict[str, Any], target: Path) -> None:
    lines = _build_pdf_lines(job, result)
    content = ["BT", "/F1 12 Tf", "50 780 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index == 0:
            content.append(f"({_escape_pdf_text(line)}) Tj")
        else:
            content.append(f"T* ({_escape_pdf_text(line)}) Tj")
    content.append("ET")
    content_stream = "\n".join(content).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii") + content_stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    target.write_bytes(pdf)


def _build_pdf_lines(job: NestingJob, result: dict[str, Any]) -> list[str]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    material = result.get("material") if isinstance(result.get("material"), dict) else {}
    payload = job.payload if isinstance(job.payload, dict) else {}
    payload_material = payload.get("material") if isinstance(payload.get("material"), dict) else {}
    payload_sheet = payload.get("sheet") if isinstance(payload.get("sheet"), dict) else {}
    parts = result.get("parts") if isinstance(result.get("parts"), list) else []
    timestamp = job.finished_at.isoformat() if job.finished_at else "unknown"
    lines = [
        "Nestora PDF Report",
        f"Job: {job.id}",
        f"Status: {result.get('status', job.state)}",
        f"Timestamp: {timestamp}",
        f"Material: {material.get('name') or payload_material.get('name') or 'Not set'}",
        f"Thickness: {_to_float(material.get('thickness') or payload_material.get('thickness'))}",
        (
            "Sheet: "
            f"{_to_float(material.get('sheet_width') or payload_material.get('sheet_width') or payload_sheet.get('width'))} x "
            f"{_to_float(material.get('sheet_height') or payload_material.get('sheet_height') or payload_sheet.get('height'))} "
            f"{material.get('units') or payload_material.get('units') or payload_sheet.get('units') or 'mm'}"
        ),
        f"Yield: {_format_percent(result.get('yield_ratio') or result.get('yield'))}",
        f"Scrap: {_format_percent(result.get('scrap_ratio'))}",
        f"Total parts placed: {int(result.get('total_parts_placed') or result.get('parts_placed') or 0)}",
    ]
    if summary:
        lines.append(f"Requested part entries: {int(summary.get('total_parts') or len(parts))}")
    lines.append("Per-part requested / placed / remaining:")
    if parts:
        for part in parts[:12]:
            if not isinstance(part, dict):
                continue
            lines.append(
                f"- {part.get('filename') or part.get('part_id')}: "
                f"{int(part.get('requested_quantity') or 0)} / {int(part.get('placed_quantity') or 0)} / {int(part.get('remaining_quantity') or 0)}"
            )
    else:
        lines.append("- No part summary available")
    return lines[:40]


def _polygon_points(value: Any) -> list[tuple[float, float]]:
    if not isinstance(value, dict):
        return []
    points = value.get("points")
    if not isinstance(points, list):
        return []
    normalized: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        x = _to_float(point.get("x"), default=math.nan)
        y = _to_float(point.get("y"), default=math.nan)
        if math.isfinite(x) and math.isfinite(y):
            normalized.append((x, y))
    return normalized


def _detect_units_code(job: NestingJob, result: dict[str, Any]) -> int:
    payload = job.payload if isinstance(job.payload, dict) else {}
    payload_material = payload.get("material") if isinstance(payload.get("material"), dict) else {}
    payload_sheet = payload.get("sheet") if isinstance(payload.get("sheet"), dict) else {}
    units = (result.get("material", {}).get("units") if isinstance(result.get("material"), dict) else None) or payload_material.get(
        "units"
    ) or payload_sheet.get("units")
    return 1 if units == "in" else 4


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _format_percent(value: Any) -> str:
    numeric = _to_float(value)
    return f"{numeric * 100:.2f}%"


def _to_float(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
