import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricsPanel } from "../features/metrics/MetricsPanel";
import { App } from "./App";

const rectangle = [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }];

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );

function buildFetchMock(options?: {
  createJobResponseMode?: "fill_sheet" | "batch_quantity";
  resultMode?: "fill_sheet" | "batch_quantity";
  resultParts?: Array<{
    part_id: string;
    filename: string;
    requested_quantity: number;
    placed_quantity: number;
    remaining_quantity: number;
    area_contribution: number;
  }>;
}) {
  const createJobResponseMode = options?.createJobResponseMode ?? "batch_quantity";
  const resultMode = options?.resultMode ?? createJobResponseMode;
  const resultParts = options?.resultParts ?? [
    {
      part_id: "part-1",
      filename: "part-a.dxf",
      requested_quantity: 3,
      placed_quantity: 1,
      remaining_quantity: 2,
      area_contribution: 200,
    },
  ];

  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
    if (url.endsWith("/v1/files/import")) {
      return jsonResponse({
        import_id: `imp-${Math.random()}`,
        filename: "part.dxf",
        polygons: [{ points: rectangle }],
        invalid_shapes: [],
        audit: {
          detected_units: "mm",
          geometry_stats: { polygon_count: 1, total_area: 200, max_extent: 20 },
          warnings: [],
        },
      });
    }
    if (url.endsWith("/v1/geometry/clean")) {
      return jsonResponse({
        polygons: [{ points: rectangle }],
        removed: 0,
        invalid_shapes: [],
      });
    }
    if (url.endsWith("/v1/nesting/jobs")) {
      return jsonResponse({ id: "job-1", state: "CREATED", error: null, mode: createJobResponseMode, summary: { total_parts: resultParts.length }, parts: [] }, 202);
    }
    if (url.endsWith("/v1/nesting/jobs/job-1")) {
      return jsonResponse({ id: "job-1", state: "SUCCEEDED", error: null, mode: resultMode, summary: { total_parts: resultParts.length }, parts: [] });
    }
    if (url.endsWith("/v1/nesting/jobs/job-1/result")) {
      return jsonResponse({
        mode: resultMode,
        summary: { total_parts: resultParts.length },
        yield: 0.5,
        scrap_area: 50,
        used_area: 50,
        total_sheet_area: 100,
        layouts: [],
        unplaced_parts: [],
        parts: resultParts,
      });
    }
    return jsonResponse({});
  });
}

async function uploadAndCleanTwoParts(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByLabelText("DXF file"), [
    new File(["a"], "part-a.dxf", { type: "application/dxf" }),
    new File(["b"], "part-b.dxf", { type: "application/dxf" }),
  ]);
  await user.click(await screen.findByRole("button", { name: "Clean Geometry" }));
}

describe("App multi-part nesting workflow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the mode selector and switches between Fill Sheet and Batch Quantity", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    render(<App />);
    const user = userEvent.setup();

    expect(await screen.findByText("Fill Sheet")).toBeInTheDocument();
    expect(screen.getByText(/The system will try to place as many parts as possible/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Batch Quantity" }));

    expect(screen.getByText(/The system will try to place the requested quantities/i)).toBeInTheDocument();
  });

  it("uploads multiple DXF files and renders them in the part list", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    render(<App />);
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), [
      new File(["a"], "part-a.dxf", { type: "application/dxf" }),
      new File(["b"], "part-b.dxf", { type: "application/dxf" }),
    ]);

    expect(await screen.findByText("part-a.dxf")).toBeInTheDocument();
    expect(await screen.findByText("part-b.dxf")).toBeInTheDocument();
    expect(screen.getAllByText(/Parsed polygons:/i).length).toBeGreaterThanOrEqual(2);
  });

  it("shows quantity inputs only in Batch Quantity mode after cleanup", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    render(<App />);
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Clean Geometry" }));

    expect(screen.queryByLabelText("Requested quantity")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Batch Quantity" }));

    expect(await screen.findByLabelText("Requested quantity")).toBeInTheDocument();
  });

  it("shows validation feedback when every part is disabled", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    render(<App />);
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Clean Geometry" }));
    await user.click(screen.getAllByLabelText("Include in nesting")[0]);

    expect(await screen.findByText("Enable at least one part before running nesting.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Nesting" })).toBeDisabled();
  });

  it("renders per-part counts in the result panel", () => {
    render(
      <MetricsPanel
        result={{
          mode: "batch_quantity",
          summary: { total_parts: 1 },
          yield: 0.75,
          scrap_area: 25,
          used_area: 75,
          total_sheet_area: 100,
          layouts: [],
          unplaced_parts: ["part-b"],
          parts: [
            {
              part_id: "part-a",
              filename: "part-a.dxf",
              requested_quantity: 5,
              placed_quantity: 3,
              remaining_quantity: 2,
              area_contribution: 300,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Nesting Mode Used")).toBeInTheDocument();
    expect(screen.getByText("Active parts in result: 1")).toBeInTheDocument();
    expect(screen.getByText("part-a.dxf")).toBeInTheDocument();
    expect(screen.getByText(/Requested:/i)).toBeInTheDocument();
    expect(screen.getByText(/Remaining:/i)).toBeInTheDocument();
    expect(screen.getByText("part-b")).toBeInTheDocument();
  });

  it("makes mixed multi-part results obvious in the result panel", () => {
    render(
      <MetricsPanel
        result={{
          mode: "fill_sheet",
          summary: { total_parts: 2 },
          yield: 0.9,
          scrap_area: 10,
          used_area: 90,
          total_sheet_area: 100,
          layouts: [],
          unplaced_parts: [],
          parts: [
            {
              part_id: "part-a",
              filename: "part-a.dxf",
              requested_quantity: 1,
              placed_quantity: 2,
              remaining_quantity: 0,
              area_contribution: 40,
            },
            {
              part_id: "part-b",
              filename: "part-b.dxf",
              requested_quantity: 1,
              placed_quantity: 1,
              remaining_quantity: 0,
              area_contribution: 50,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Mixed sheet result detected")).toBeInTheDocument();
    expect(screen.getByText("2 part types were placed in this job result.")).toBeInTheDocument();
  });

  it("shows Fill Sheet results as repeated placements instead of a single-copy outcome", () => {
    render(
      <MetricsPanel
        result={{
          mode: "fill_sheet",
          summary: { total_parts: 1 },
          yield: 1,
          scrap_area: 0,
          used_area: 20000,
          total_sheet_area: 20000,
          parts_placed: 20,
          total_parts_placed: 20,
          layouts: [],
          unplaced_parts: [],
          parts: [
            {
              part_id: "plate",
              filename: "plate.dxf",
              requested_quantity: 1,
              placed_quantity: 20,
              remaining_quantity: 0,
              area_contribution: 20000,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Fill Sheet")).toBeInTheDocument();
    expect(screen.getByText("Repeated fill result confirmed")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.getByText(/Placed:/i)).toBeInTheDocument();
    expect(screen.getByText(/Remaining:/i)).toBeInTheDocument();
  });

  it("keeps the run button disabled until at least one cleaned part is enabled", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    render(<App />);
    const user = userEvent.setup();

    const runButton = screen.getByRole("button", { name: "Run Nesting" });
    expect(runButton).toBeDisabled();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Clean Geometry" }));

    await waitFor(() => expect(runButton).toBeEnabled());
  });

  it("submits a successful Fill Sheet multi-part job with the new request contract", async () => {
    const fetchMock = buildFetchMock({
      createJobResponseMode: "fill_sheet",
      resultMode: "fill_sheet",
      resultParts: [
        {
          part_id: "part-1",
          filename: "part-a.dxf",
          requested_quantity: 1,
          placed_quantity: 1,
          remaining_quantity: 0,
          area_contribution: 200,
        },
        {
          part_id: "part-2",
          filename: "part-b.dxf",
          requested_quantity: 1,
          placed_quantity: 1,
          remaining_quantity: 0,
          area_contribution: 200,
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup();

    await uploadAndCleanTwoParts(user);
    await user.click(screen.getByRole("button", { name: "Run Nesting" }));

    await screen.findByText("Active parts in result: 2");

    const createCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/v1/nesting/jobs"));
    expect(createCall).toBeTruthy();
    const requestBody = JSON.parse(String((createCall?.[1] as RequestInit).body));
    expect(requestBody.mode).toBe("fill_sheet");
    expect(requestBody.sheet.units).toBe("mm");
    expect(requestBody.parts).toHaveLength(2);
    expect(requestBody.parts[0].filename).toBe("part-a.dxf");
    expect(requestBody.parts[0].quantity).toBeUndefined();
    expect(requestBody.parts[0].fill_only).toBe(false);
    expect(requestBody.parts[1].filename).toBe("part-b.dxf");
  });

  it("submits a successful Batch Quantity multi-part job with requested quantities", async () => {
    const fetchMock = buildFetchMock({
      createJobResponseMode: "batch_quantity",
      resultMode: "batch_quantity",
      resultParts: [
        {
          part_id: "part-1",
          filename: "part-a.dxf",
          requested_quantity: 5,
          placed_quantity: 1,
          remaining_quantity: 4,
          area_contribution: 200,
        },
        {
          part_id: "part-2",
          filename: "part-b.dxf",
          requested_quantity: 2,
          placed_quantity: 1,
          remaining_quantity: 1,
          area_contribution: 200,
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup();

    await uploadAndCleanTwoParts(user);
    await user.click(screen.getByRole("button", { name: "Batch Quantity" }));
    const quantityInputs = await screen.findAllByLabelText("Requested quantity");
    await user.clear(quantityInputs[0]);
    await user.type(quantityInputs[0], "5");
    await user.clear(quantityInputs[1]);
    await user.type(quantityInputs[1], "2");
    await user.click(screen.getByRole("button", { name: "Run Nesting" }));

    await screen.findByText("Active parts in result: 2");

    const createCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/v1/nesting/jobs"));
    expect(createCall).toBeTruthy();
    const requestBody = JSON.parse(String((createCall?.[1] as RequestInit).body));
    expect(requestBody.mode).toBe("batch_quantity");
    expect(requestBody.parts).toHaveLength(2);
    expect(requestBody.parts[0].quantity).toBe(5);
    expect(requestBody.parts[0].fill_only).toBe(false);
    expect(requestBody.parts[1].quantity).toBe(2);
    expect(screen.getByText("part-a.dxf")).toBeInTheDocument();
    expect(screen.getAllByText(/Remaining:/i).length).toBeGreaterThan(0);
  });

  it("explains partial-fit batch results clearly in the result panel", () => {
    render(
      <MetricsPanel
        result={{
          mode: "batch_quantity",
          summary: { total_parts: 1 },
          yield: 0.8,
          scrap_area: 20,
          used_area: 80,
          total_sheet_area: 100,
          parts_placed: 4,
          total_parts_placed: 4,
          layouts: [],
          unplaced_parts: ["panel"],
          parts: [
            {
              part_id: "panel",
              filename: "panel.dxf",
              requested_quantity: 5,
              placed_quantity: 4,
              remaining_quantity: 1,
              area_contribution: 80,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Partial-fit batch result")).toBeInTheDocument();
    expect(screen.getByText("Parts that did not fully fit:")).toBeInTheDocument();
    expect(screen.getByText("panel")).toBeInTheDocument();
    expect(screen.getByText(/Remaining:/i)).toBeInTheDocument();
  });
});
