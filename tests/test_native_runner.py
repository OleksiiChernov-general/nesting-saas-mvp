from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from app.native_runner import NativePOCResult, NativeRunnerError, NativeRunnerUnsupportedResult, ensure_native_result_ready, run_native_poc, run_native_poc_safe
from app.nesting import PartSpec, SheetSpec
from app.settings import get_settings


def _sample_parts() -> list[PartSpec]:
    return [
        PartSpec(
            part_id="part-1",
            filename="part-1.dxf",
            polygon=Polygon([(0, 0), (10, 0), (10, 10), (0, 0)]),
            quantity=1,
        )
    ]


def _sample_sheets() -> list[SheetSpec]:
    return [SheetSpec(sheet_id="sheet-1", width=100, height=100, quantity=1)]


def test_run_native_poc_raises_structured_error_and_writes_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_executable", tmp_path / "fake.exe")
    settings.native_poc_executable.write_text("", encoding="utf-8")

    structured_error = {
        "error_type": "std_exception",
        "message": "Error while merging geometries!",
        "backtrace": "",
        "input_digest": "fnv1a64:deadbeef",
    }

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=kwargs.get("args", ["fake.exe"]),
            returncode=1,
            stdout=json.dumps(structured_error),
            stderr="debug stage=before_nest invoke=true",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(NativeRunnerError) as excinfo:
        run_native_poc(
            _sample_parts(),
            _sample_sheets(),
            {"mode": "fill_sheet", "gap": 2.0, "rotation": [0], "time_limit_sec": 60.0},
            artifact_dir=tmp_path / "artifacts",
        )

    error = excinfo.value
    assert error.error_type == "std_exception"
    assert error.exit_code == 1
    assert error.artifact_dir == tmp_path / "artifacts"
    assert error.error_payload["status"] == "ERROR"
    assert error.error_payload["error_code"] == "std_exception"
    assert error.error_payload["details"]["stderr_excerpt"] == "debug stage=before_nest invoke=true"
    assert (tmp_path / "artifacts" / "input.json").exists()
    assert (tmp_path / "artifacts" / "stdout.txt").read_text(encoding="utf-8") == json.dumps(structured_error)
    assert "Error while merging geometries!" in error.message


def test_run_native_poc_times_out_with_structured_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_executable", tmp_path / "fake.exe")
    settings.native_poc_executable.write_text("", encoding="utf-8")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", ["fake.exe"]), timeout=60.0, output="partial", stderr="still running")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(NativeRunnerError) as excinfo:
        run_native_poc(
            _sample_parts(),
            _sample_sheets(),
            {"mode": "fill_sheet", "gap": 2.0, "rotation": [0], "time_limit_sec": 120.0},
            artifact_dir=tmp_path / "artifacts",
        )

    error = excinfo.value
    assert error.error_type == "timeout"
    assert error.exit_code is None
    assert error.artifact_dir == tmp_path / "artifacts"
    meta = json.loads((tmp_path / "artifacts" / "meta.json").read_text(encoding="utf-8"))
    assert meta["timeout_seconds"] == 60.0
    assert meta["binary_path"].endswith("fake.exe")
    assert error.error_payload["details"]["stdout_excerpt"] == "partial"


def test_run_native_poc_safe_returns_structured_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_executable", tmp_path / "fake.exe")
    settings.native_poc_executable.write_text("", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=kwargs.get("args", ["fake.exe"]),
            returncode=0xC0000135,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = run_native_poc_safe(
        _sample_parts(),
        _sample_sheets(),
        {"mode": "fill_sheet", "gap": 2.0, "rotation": [0], "time_limit_sec": 60.0},
        artifact_dir=tmp_path / "artifacts",
    )

    assert response["status"] == "ERROR"
    assert response["error_code"] == "process_crash"
    assert response["message"] == "Native POC failed to start because a required DLL was not found"


def test_run_native_poc_parses_json_after_debug_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "native_poc_executable", tmp_path / "fake.exe")
    settings.native_poc_executable.write_text("", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=kwargs.get("args", ["fake.exe"]),
            returncode=0,
            stdout='debug prefix ignored {"status":"PARSED_READY_FOR_ADAPTER","backend_name":"summary_stub","backend_available":false,"converted_part_count":1,"placement_count":0,"bins_used":0}',
            stderr="debug stage=after_parse",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_native_poc(
        _sample_parts(),
        _sample_sheets(),
        {"mode": "fill_sheet", "gap": 2.0, "rotation": [0], "time_limit_sec": 60.0},
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.status == "PARSED_READY_FOR_ADAPTER"
    assert result.backend_name == "summary_stub"


def test_ensure_native_result_ready_rejects_non_layout_summary_payload(tmp_path: Path) -> None:
    result = NativePOCResult(
        status="PARSED_READY_FOR_ADAPTER",
        backend_name="summary_stub",
        backend_available=True,
        converted_part_count=1,
        placement_count=0,
        bins_used=0,
        payload={"status": "PARSED_READY_FOR_ADAPTER", "backend_available": True},
        stdout="{}",
        stderr="",
        exit_code=0,
        input_digest="sha256:test",
        artifact_dir=tmp_path,
    )

    with pytest.raises(NativeRunnerUnsupportedResult) as excinfo:
        ensure_native_result_ready(result)

    assert excinfo.value.error_type == "unsupported_result"
    assert "stable job result payload" in excinfo.value.message
