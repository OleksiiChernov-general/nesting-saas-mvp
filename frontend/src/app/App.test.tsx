import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricsPanel } from "../features/metrics/MetricsPanel";
import { LayoutViewer } from "../features/viewer/LayoutViewer";
import { App } from "./App";

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("renders the app shell", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ status: "ok" })));

    render(<App />);

    expect((await screen.findAllByText("Nesting SaaS MVP")).length).toBeGreaterThan(0);
    expect(screen.getByText("Upload DXF")).toBeInTheDocument();
    expect(screen.getByText("Layout Viewer")).toBeInTheDocument();
  });

  it("renders disconnected state when health check fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));

    render(<App />);

    expect(await screen.findByText("Disconnected")).toBeInTheDocument();
    expect(screen.getByText(/Backend connection failed/i)).toBeInTheDocument();
  });

  it("keeps workflow actions disabled until prerequisites are met", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
      if (url.endsWith("/v1/files/import")) {
        return jsonResponse({
          import_id: "imp-1",
          filename: "sample.dxf",
          polygons: [{ points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }] }],
          invalid_shapes: [],
        });
      }
      if (url.endsWith("/v1/geometry/clean") && init?.method === "POST") {
        return jsonResponse({
          polygons: [{ points: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }] }],
          removed: 0,
          invalid_shapes: [],
        });
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const cleanButton = await screen.findByRole("button", { name: "Clean Geometry" });
    const runButton = screen.getByRole("button", { name: "Run Nesting" });

    expect(cleanButton).toBeDisabled();
    expect(runButton).toBeDisabled();

    await user.upload(screen.getByLabelText("DXF file"), new File(["dxf"], "sample.dxf", { type: "application/dxf" }));
    await user.click(screen.getByRole("button", { name: "Upload File" }));

    await waitFor(() => expect(cleanButton).toBeEnabled());
    await user.click(cleanButton);
    await waitFor(() => expect(runButton).toBeEnabled());
  });

  it("shows successful job status transition and metrics", async () => {
    vi.useFakeTimers();

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
      if (url.endsWith("/v1/files/import")) {
        return jsonResponse({
          import_id: "imp-1",
          filename: "sample.dxf",
          polygons: [{ points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }] }],
          invalid_shapes: [],
        });
      }
      if (url.endsWith("/v1/geometry/clean")) {
        return jsonResponse({
          polygons: [{ points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }] }],
          removed: 0,
          invalid_shapes: [],
        });
      }
      if (url.endsWith("/v1/nesting/jobs")) {
        return jsonResponse({ id: "job-1", state: "CREATED", error: null }, 202);
      }
      if (url.endsWith("/v1/nesting/jobs/job-1")) {
        const count = fetchMock.mock.calls.filter(([callUrl]) => String(callUrl).endsWith("/v1/nesting/jobs/job-1")).length;
        return jsonResponse({ id: "job-1", state: count > 1 ? "SUCCEEDED" : "RUNNING", error: null });
      }
      if (url.endsWith("/v1/nesting/jobs/job-1/result")) {
        return jsonResponse({
          yield: 0.82,
          scrap_area: 18,
          used_area: 82,
          total_sheet_area: 100,
          layouts: [
            {
              sheet_id: "sheet-1",
              instance: 1,
              width: 100,
              height: 100,
              used_area: 82,
              scrap_area: 18,
              placements: [
                {
                  part_id: "part-1",
                  sheet_id: "sheet-1",
                  instance: 1,
                  rotation: 0,
                  x: 0,
                  y: 0,
                  width: 20,
                  height: 10,
                  polygon: {
                    points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }],
                  },
                },
              ],
            },
          ],
          unplaced_parts: [],
        });
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.upload(screen.getByLabelText("DXF file"), new File(["dxf"], "sample.dxf", { type: "application/dxf" }));
    await user.click(screen.getByRole("button", { name: "Upload File" }));
    await user.click(await screen.findByRole("button", { name: "Clean Geometry" }));
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    expect(await screen.findByText("CREATED")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(1600);
    });

    await waitFor(() => expect(screen.getByText("SUCCEEDED")).toBeInTheDocument());
    expect(screen.getByText("82.0%")).toBeInTheDocument();
    expect(screen.getByText("Job completed successfully.")).toBeInTheDocument();
  });

  it("shows failed job status transition and allows rerun messaging", async () => {
    vi.useFakeTimers();

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
      if (url.endsWith("/v1/files/import")) {
        return jsonResponse({
          import_id: "imp-1",
          filename: "sample.dxf",
          polygons: [{ points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }] }],
          invalid_shapes: [],
        });
      }
      if (url.endsWith("/v1/geometry/clean")) {
        return jsonResponse({
          polygons: [{ points: [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }] }],
          removed: 0,
          invalid_shapes: [],
        });
      }
      if (url.endsWith("/v1/nesting/jobs")) {
        return jsonResponse({ id: "job-2", state: "CREATED", error: null }, 202);
      }
      if (url.endsWith("/v1/nesting/jobs/job-2")) {
        return jsonResponse({ id: "job-2", state: "FAILED", error: "Placement failed" });
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.upload(screen.getByLabelText("DXF file"), new File(["dxf"], "sample.dxf", { type: "application/dxf" }));
    await user.click(screen.getByRole("button", { name: "Upload File" }));
    await user.click(await screen.findByRole("button", { name: "Clean Geometry" }));
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    await waitFor(() => expect(screen.getByText("FAILED")).toBeInTheDocument());
    expect(screen.getByText("Placement failed")).toBeInTheDocument();
    expect(screen.getByText("Previous job failed. Update inputs if needed and run again.")).toBeInTheDocument();
  });

  it("renders metrics panel values", () => {
    render(
      <MetricsPanel
        result={{
          yield: 0.75,
          scrap_area: 25,
          used_area: 75,
          total_sheet_area: 100,
          layouts: [{ sheet_id: "sheet-1", instance: 1, width: 100, height: 100, used_area: 75, scrap_area: 25, placements: [] }],
          unplaced_parts: [],
        }}
      />,
    );

    expect(screen.getByText("75.0%")).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
    expect(screen.getByText("Layouts used")).toBeInTheDocument();
  });

  it("renders viewer fallback for empty layout", () => {
    render(
      <LayoutViewer
        activeSheetIndex={0}
        canShowResult={true}
        layouts={[{ sheet_id: "sheet-1", instance: 1, width: 100, height: 100, used_area: 0, scrap_area: 100, placements: [] }]}
        onSheetChange={() => undefined}
        previewPolygons={[]}
      />,
    );

    expect(screen.getByText("No parts placed on this sheet.")).toBeInTheDocument();
  });

  it("runs one mocked integration-style flow end to end", async () => {
    vi.useFakeTimers();

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
      if (url.endsWith("/v1/files/import")) {
        return jsonResponse({
          import_id: "imp-7",
          filename: "demo.dxf",
          polygons: [{ points: [{ x: -5, y: -5 }, { x: 25, y: -5 }, { x: 25, y: 15 }, { x: -5, y: 15 }, { x: -5, y: -5 }] }],
          invalid_shapes: [{ source: "arc", reason: "Approximated" }],
        });
      }
      if (url.endsWith("/v1/geometry/clean")) {
        return jsonResponse({
          polygons: [{ points: [{ x: -5, y: -5 }, { x: 25, y: -5 }, { x: 25, y: 15 }, { x: -5, y: 15 }, { x: -5, y: -5 }] }],
          removed: 0,
          invalid_shapes: [],
        });
      }
      if (url.endsWith("/v1/nesting/jobs")) {
        return jsonResponse({ id: "job-7", state: "CREATED", error: null }, 202);
      }
      if (url.endsWith("/v1/nesting/jobs/job-7")) {
        const count = fetchMock.mock.calls.filter(([callUrl]) => String(callUrl).endsWith("/v1/nesting/jobs/job-7")).length;
        return jsonResponse({ id: "job-7", state: count > 1 ? "SUCCEEDED" : "RUNNING", error: null });
      }
      if (url.endsWith("/v1/nesting/jobs/job-7/result")) {
        return jsonResponse({
          yield_value: 0.5,
          scrap_area: 50,
          used_area: 50,
          total_sheet_area: 100,
          layouts: [
            {
              sheet_id: "",
              instance: 1,
              width: 100,
              height: 100,
              used_area: 50,
              scrap_area: 50,
              placements: [
                {
                  part_id: "",
                  sheet_id: "",
                  instance: 1,
                  rotation: 0,
                  x: -5,
                  y: -5,
                  width: 30,
                  height: 20,
                  polygon: {
                    points: [{ x: -5, y: -5 }, { x: 25, y: -5 }, { x: 25, y: 15 }, { x: -5, y: 15 }, { x: -5, y: -5 }],
                  },
                },
              ],
            },
          ],
          unplaced_parts: ["part-x"],
        });
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.upload(screen.getByLabelText("DXF file"), new File(["dxf"], "demo.dxf", { type: "application/dxf" }));
    await user.click(screen.getByRole("button", { name: "Upload File" }));
    await waitFor(() => expect(screen.getByText("Imported: demo.dxf")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Clean Geometry" }));
    await user.click(screen.getByRole("button", { name: "Run Nesting" }));

    await act(async () => {
      vi.advanceTimersByTime(1600);
    });

    await waitFor(() => expect(screen.getByText("SUCCEEDED")).toBeInTheDocument());
    expect(screen.getByText("Unplaced parts: part-x")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
  });
});
