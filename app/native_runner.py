from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.geometry import polygon_to_points
from app.nesting import PartSpec, SheetSpec
from app.settings import get_settings

logger = logging.getLogger(__name__)


class NativeRunnerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "native_runner_error",
        backtrace: str = "",
        input_digest: str | None = None,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        artifact_dir: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.backtrace = backtrace
        self.input_digest = input_digest
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.artifact_dir = artifact_dir

    @property
    def error_payload(self) -> dict[str, Any]:
        details = {
            "backtrace": self.backtrace,
            "input_digest": self.input_digest,
            "exit_code": self.exit_code,
            "artifact_dir": str(self.artifact_dir) if self.artifact_dir else None,
            "stdout_excerpt": _truncate_text(self.stdout),
            "stderr_excerpt": _truncate_text(self.stderr),
        }
        return {
            "status": "ERROR",
            "error_code": self.error_type,
            "details": details,
            "error_type": self.error_type,
            "message": self.message,
            "backtrace": self.backtrace,
            "input_digest": self.input_digest,
            "exit_code": self.exit_code,
            "artifact_dir": details["artifact_dir"],
        }

    def __str__(self) -> str:
        return json.dumps(self.error_payload, ensure_ascii=False)


class NativeRunnerUnsupportedResult(NativeRunnerError):
    def __init__(
        self,
        message: str,
        *,
        input_digest: str | None = None,
        stdout: str = "",
        stderr: str = "",
        artifact_dir: Path | None = None,
    ) -> None:
        super().__init__(
            message,
            error_type="unsupported_result",
            input_digest=input_digest,
            stdout=stdout,
            stderr=stderr,
            artifact_dir=artifact_dir,
        )


@dataclass
class NativePOCResult:
    status: str
    backend_name: str
    backend_available: bool
    converted_part_count: int
    placement_count: int
    bins_used: int
    payload: dict[str, Any]
    stdout: str
    stderr: str
    exit_code: int
    input_digest: str
    artifact_dir: Path | None

    @property
    def response_payload(self) -> dict[str, Any]:
        return {
            "status": "OK",
            "result": self.payload,
            "details": {
                "backend_name": self.backend_name,
                "backend_available": self.backend_available,
                "placement_count": self.placement_count,
                "bins_used": self.bins_used,
                "converted_part_count": self.converted_part_count,
                "exit_code": self.exit_code,
                "input_digest": self.input_digest,
                "artifact_dir": str(self.artifact_dir) if self.artifact_dir else None,
                "stdout_excerpt": _truncate_text(self.stdout),
                "stderr_excerpt": _truncate_text(self.stderr),
            },
        }


def _truncate_text(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"


def _point_payload(points: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"x": float(x), "y": float(y)} for x, y in points]


def build_native_poc_payload(parts: list[PartSpec], sheets: list[SheetSpec], params: dict[str, Any]) -> dict[str, Any]:
    if not sheets:
        raise NativeRunnerError("At least one sheet is required for native POC payload")

    sheet = sheets[0]
    payload = {
        "sheet": {
            "width": float(sheet.width),
            "height": float(sheet.height),
        },
        "parts": [
            {
                "part_id": part.part_id,
                "filename": part.filename,
                "quantity": int(part.quantity),
                "polygon": {
                    "points": _point_payload(polygon_to_points(part.polygon)),
                },
            }
            for part in parts
        ],
        "params": {
            "mode": str(params.get("mode", "batch_quantity")),
            "gap": float(params.get("gap", 0.0)),
            "rotation": list(params.get("rotation", [0])),
            "time_limit_sec": float(params.get("time_limit_sec", get_settings().max_compute_seconds)),
        },
    }
    return payload


def _stable_payload_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _input_digest(payload_text: str) -> str:
    return f"sha256:{hashlib.sha256(payload_text.encode('utf-8')).hexdigest()}"


def _native_timeout_seconds(params: dict[str, Any], settings) -> float:
    requested = float(params.get("time_limit_sec", settings.max_compute_seconds))
    return max(1.0, min(requested, settings.max_compute_seconds, 60.0))


def _default_artifact_dir(base_dir: Path, input_digest: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest_suffix = input_digest.split(":")[-1][:12]
    return base_dir / "native_poc_runs" / f"{timestamp}_{digest_suffix}"


def _native_vendor_bin_candidates(binary: Path) -> list[Path]:
    resolved = binary.resolve()
    repo_vendor_bin = Path(__file__).resolve().parent.parent / "native" / "libnest2d-poc" / "third_party" / "vendor-prefix" / "bin"
    candidates = [
        resolved.parent.parent / "third_party" / "vendor-prefix" / "bin",
        resolved.parent.parent.parent / "third_party" / "vendor-prefix" / "bin",
        repo_vendor_bin,
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _write_artifacts(
    artifact_dir: Path | None,
    *,
    binary_path: Path,
    vendor_bins: list[Path],
    payload_text: str,
    stdout_text: str,
    stderr_text: str,
    exit_code: int | None,
    timeout_seconds: float,
    input_digest: str,
) -> Path | None:
    if artifact_dir is None:
        return None

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "input.json").write_text(payload_text, encoding="utf-8")
    (artifact_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    (artifact_dir / "meta.json").write_text(
        json.dumps(
            {
                "input_digest": input_digest,
                "exit_code": exit_code,
                "timeout_seconds": timeout_seconds,
                "binary_path": str(binary_path),
                "vendor_bins": [str(path) for path in vendor_bins],
                "stdout_excerpt": _truncate_text(stdout_text),
                "stderr_excerpt": _truncate_text(stderr_text),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return artifact_dir


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if not candidate:
        return None
    probe_candidates = [candidate]
    if "{" in candidate:
        probe_candidates.append(candidate[candidate.find("{") :])
    for probe in probe_candidates:
        probe = probe.strip()
        if not probe:
            continue
        try:
            parsed = json.loads(probe)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_structured_error(stdout_text: str, stderr_text: str, input_digest: str) -> dict[str, Any] | None:
    for candidate in (stdout_text, stderr_text):
        parsed = _extract_json_object(candidate)
        if parsed is None:
            continue
        if isinstance(parsed, dict) and {"error_type", "message", "backtrace", "input_digest"} <= parsed.keys():
            parsed.setdefault("input_digest", input_digest)
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
            error = parsed["error"]
            if {"error_type", "message"} <= error.keys():
                error.setdefault("backtrace", "")
                error.setdefault("input_digest", input_digest)
                return error
    return None


def _raise_native_error(
    *,
    message: str,
    error_type: str,
    input_digest: str,
    stdout_text: str,
    stderr_text: str,
    exit_code: int | None,
    artifact_dir: Path | None,
    backtrace: str = "",
) -> None:
    raise NativeRunnerError(
        message,
        error_type=error_type,
        backtrace=backtrace,
        input_digest=input_digest,
        exit_code=exit_code,
        stdout=stdout_text,
        stderr=stderr_text,
        artifact_dir=artifact_dir,
    )


def _classify_exit_code(exit_code: int, stderr_text: str, stdout_text: str) -> tuple[str, str]:
    if exit_code == 0xC0000135:
        return "process_crash", "Native POC failed to start because a required DLL was not found"
    if exit_code == 0xC0000005:
        return "process_crash", "Native POC crashed with access violation"
    if exit_code < 0:
        return "process_crash", f"Native POC terminated by signal {-exit_code}"
    if not stderr_text.strip() and not stdout_text.strip():
        return "process_crash", f"Native POC exited with code {exit_code}"
    return "nonzero_exit", (stderr_text.strip() or stdout_text.strip() or "Native POC process failed")


def run_native_poc(
    parts: list[PartSpec],
    sheets: list[SheetSpec],
    params: dict[str, Any],
    executable: Path | None = None,
    artifact_dir: Path | None = None,
) -> NativePOCResult:
    settings = get_settings()
    binary = Path(executable or settings.native_poc_executable)
    if not binary.exists():
        raise NativeRunnerError(f"Native POC executable not found: {binary}")

    payload = build_native_poc_payload(parts, sheets, params)
    payload_text = _stable_payload_text(payload)
    input_digest = _input_digest(payload_text)
    timeout_seconds = _native_timeout_seconds(params, settings)
    artifact_root = artifact_dir or _default_artifact_dir(settings.storage_dir, input_digest)

    env = dict(os.environ)
    vendor_bins = [path for path in _native_vendor_bin_candidates(binary) if path.exists()]
    if vendor_bins:
        env["PATH"] = f"{os.pathsep.join(str(path) for path in vendor_bins)}{os.pathsep}{env.get('PATH', '')}"
    logger.info(
        "Running native POC binary=%s timeout=%.1fs input_digest=%s vendor_bins=%s",
        binary,
        timeout_seconds,
        input_digest,
        [str(path) for path in vendor_bins],
    )

    try:
        completed = subprocess.run(
            [str(binary)],
            input=payload_text,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=str(binary.parent),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        written_artifact_dir = _write_artifacts(
            artifact_root,
            binary_path=binary,
            vendor_bins=vendor_bins,
            payload_text=payload_text,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            exit_code=None,
            timeout_seconds=timeout_seconds,
            input_digest=input_digest,
        )
        _raise_native_error(
            message=f"Native POC timed out after {timeout_seconds:.1f}s",
            error_type="timeout",
            input_digest=input_digest,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            exit_code=None,
            artifact_dir=written_artifact_dir,
        )

    written_artifact_dir = _write_artifacts(
        artifact_root,
        binary_path=binary,
        vendor_bins=vendor_bins,
        payload_text=payload_text,
        stdout_text=completed.stdout,
        stderr_text=completed.stderr,
        exit_code=completed.returncode,
        timeout_seconds=timeout_seconds,
        input_digest=input_digest,
    )

    structured_error = _extract_structured_error(completed.stdout, completed.stderr, input_digest)
    if completed.returncode != 0:
        if structured_error:
            _raise_native_error(
                message=str(structured_error.get("message") or "Native POC returned a structured error"),
                error_type=str(structured_error.get("error_type") or "native_error"),
                input_digest=str(structured_error.get("input_digest") or input_digest),
                stdout_text=completed.stdout,
                stderr_text=completed.stderr,
                exit_code=completed.returncode,
                artifact_dir=written_artifact_dir,
                backtrace=str(structured_error.get("backtrace") or ""),
            )
        error_type, message = _classify_exit_code(completed.returncode, completed.stderr, completed.stdout)
        _raise_native_error(
            message=message,
            error_type=error_type,
            input_digest=input_digest,
            stdout_text=completed.stdout,
            stderr_text=completed.stderr,
            exit_code=completed.returncode,
            artifact_dir=written_artifact_dir,
        )

    try:
        response = _extract_json_object(completed.stdout)
        if response is None:
            raise json.JSONDecodeError("No JSON object found in native stdout", completed.stdout, 0)
    except json.JSONDecodeError as exc:
        _raise_native_error(
            message="Native POC returned invalid JSON",
            error_type="invalid_json",
            input_digest=input_digest,
            stdout_text=completed.stdout,
            stderr_text=completed.stderr,
            exit_code=completed.returncode,
            artifact_dir=written_artifact_dir,
        )
        raise exc

    if isinstance(response, dict) and "error_type" in response and "message" in response:
        _raise_native_error(
            message=str(response.get("message") or "Native POC returned a structured error"),
            error_type=str(response.get("error_type") or "native_error"),
            input_digest=str(response.get("input_digest") or input_digest),
            stdout_text=completed.stdout,
            stderr_text=completed.stderr,
            exit_code=completed.returncode,
            artifact_dir=written_artifact_dir,
            backtrace=str(response.get("backtrace") or ""),
        )

    return NativePOCResult(
        status=str(response.get("status", "UNKNOWN")),
        backend_name=str(response.get("backend_name", "unknown")),
        backend_available=bool(response.get("backend_available", False)),
        converted_part_count=int(response.get("converted_part_count", 0)),
        placement_count=int(response.get("placement_count", 0)),
        bins_used=int(response.get("bins_used", 0)),
        payload=response,
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        input_digest=input_digest,
        artifact_dir=written_artifact_dir,
    )


def run_native_poc_safe(
    parts: list[PartSpec],
    sheets: list[SheetSpec],
    params: dict[str, Any],
    executable: Path | None = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    try:
        return run_native_poc(parts, sheets, params, executable=executable, artifact_dir=artifact_dir).response_payload
    except NativeRunnerError as error:
        return error.error_payload


def ensure_native_result_ready(result: NativePOCResult) -> NativePOCResult:
    payload = result.payload if isinstance(result.payload, dict) else {}
    if payload.get("layouts") and payload.get("parts"):
        return result

    if result.backend_available:
        raise NativeRunnerUnsupportedResult(
            "Native backend returned diagnostics but not a stable job result payload.",
            input_digest=result.input_digest,
            stdout=result.stdout,
            stderr=result.stderr,
            artifact_dir=result.artifact_dir,
        )

    raise NativeRunnerUnsupportedResult(
        "Native backend is unavailable.",
        input_digest=result.input_digest,
        stdout=result.stdout,
        stderr=result.stderr,
        artifact_dir=result.artifact_dir,
    )
