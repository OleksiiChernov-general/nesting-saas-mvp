import type {
  CleanGeometryResponse,
  HealthResponse,
  ImportResponse,
  JobResponse,
  NestingJobCreateRequest,
  NestingResultResponse,
  PolygonPayload,
} from "../types/api";
import { API_BASE_URL } from "./config";
import {
  normalizeCleanupResponse,
  normalizeHealthResponse,
  normalizeImportResponse,
  normalizeJobResponse,
  normalizeResultResponse,
} from "./normalizers";

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError("Backend is unavailable. Start the API and check VITE_API_BASE_URL.");
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  let payload: unknown = null;
  if (isJson) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const message =
      typeof (payload as { detail?: unknown } | null)?.detail === "string"
        ? ((payload as { detail: string }).detail)
        : typeof (payload as { message?: unknown } | null)?.message === "string"
          ? ((payload as { message: string }).message)
          : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return payload;
}

export const apiClient = {
  artifactUrl(jobId: string): string {
    return `${API_BASE_URL}/v1/nesting/jobs/${jobId}/artifact`;
  },

  async health(): Promise<HealthResponse> {
    return normalizeHealthResponse(await request("/health"));
  },

  async importFile(file: File): Promise<ImportResponse> {
    const body = new FormData();
    body.append("file", file);
    const response = await request("/v1/files/import", {
      method: "POST",
      body,
    });
    return normalizeImportResponse(response, file.name);
  },

  async cleanGeometry(polygons: PolygonPayload[]): Promise<CleanGeometryResponse> {
    const response = await request("/v1/geometry/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ polygons, tolerance: 0.5 }),
    });
    return normalizeCleanupResponse(response);
  },

  async createJob(payload: NestingJobCreateRequest): Promise<JobResponse> {
    return normalizeJobResponse(
      await request("/v1/nesting/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    );
  },

  async getJob(jobId: string): Promise<JobResponse> {
    return normalizeJobResponse(await request(`/v1/nesting/jobs/${jobId}`));
  },

  async getResult(jobId: string): Promise<NestingResultResponse> {
    return normalizeResultResponse(await request(`/v1/nesting/jobs/${jobId}/result`));
  },
};
