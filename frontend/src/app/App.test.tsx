import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { translate, type AppLanguage } from "../i18n";

const rectangle = [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }];

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );

function buildFetchMock(options?: {
  importPolygons?: number;
  cleanPolygons?: number;
  importStatus?: number;
  importDetail?: string;
  resultArtifacts?: Array<{
    kind: "json" | "dxf" | "pdf";
    label: string;
    status: "available" | "processing" | "failed" | "unavailable";
    url?: string;
    message: string;
  }>;
}) {
  const importPolygons = options?.importPolygons ?? 1;
  const cleanPolygons = options?.cleanPolygons ?? importPolygons;
  const materials = [
    {
      material_id: "preset-mild-steel-3mm",
      name: "Mild Steel 3 mm",
      thickness: 3,
      sheet_width: 3000,
      sheet_height: 1500,
      units: "mm",
      kerf: 2,
      cost_per_sheet: 120,
      currency: "USD",
      notes: "Default production steel preset.",
      created_at: "2026-04-02T00:00:00Z",
      updated_at: "2026-04-02T00:00:00Z",
    },
  ];
  let createJobPayload: unknown = null;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method?.toUpperCase() ?? "GET";
    if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
    if (url.endsWith("/v1/materials") && method === "GET") return jsonResponse(materials);
    if (url.endsWith("/v1/materials") && method === "POST") return jsonResponse(materials[0], 201);
    if (url.endsWith("/v1/files/import")) {
      if (options?.importStatus && options.importStatus >= 400) {
        return jsonResponse({ detail: options.importDetail ?? "Upload failed" }, options.importStatus);
      }
      return jsonResponse({
        import_id: "imp-1",
        filename: "part.dxf",
        polygons: Array.from({ length: importPolygons }, () => ({ points: rectangle })),
        invalid_shapes: [],
        audit: {
          detected_units: "mm",
          geometry_stats: { polygon_count: importPolygons, total_area: 200, max_extent: 20 },
          warnings: [],
        },
      });
    }
    if (url.endsWith("/v1/geometry/clean")) {
      return jsonResponse({
        polygons: Array.from({ length: cleanPolygons }, () => ({ points: rectangle })),
        removed: 0,
        invalid_shapes: [],
      });
    }
    if (url.endsWith("/v1/nesting/jobs")) {
      createJobPayload = init?.body ? JSON.parse(String(init.body)) : null;
      return jsonResponse(
        { id: "job-1", state: "CREATED", error: null, mode: "fill_sheet", summary: { total_parts: 1 }, parts: [], batch: { batch_id: "batch-current", batch_name: "Current batch", orders: [] } },
        202,
      );
    }
    if (url.includes("/v1/materials/")) {
      return jsonResponse(
        {
          ...materials[0],
          name: "Mild Steel Updated",
        },
      );
    }
    if (url.endsWith("/v1/nesting/jobs/job-1")) {
      return jsonResponse({ id: "job-1", state: "SUCCEEDED", error: null, mode: "fill_sheet", summary: { total_parts: 1 }, parts: [] });
    }
    if (url.endsWith("/v1/nesting/jobs/job-1/result")) {
      return jsonResponse({
        status: "SUCCEEDED",
        mode: "fill_sheet",
        summary: { total_parts: 1 },
        yield: 0.85,
        yield_ratio: 0.85,
        scrap_ratio: 0.15,
        scrap_area: 15,
        used_area: 85,
        total_sheet_area: 100,
        total_parts_placed: 4,
        layouts: [],
        artifacts:
          options?.resultArtifacts ?? [
            { kind: "json", label: "JSON result", status: "available", url: "/v1/nesting/jobs/job-1/artifact", message: "JSON result is ready to download from the current job." },
            { kind: "dxf", label: "DXF layout", status: "available", url: "/v1/nesting/jobs/job-1/artifact/dxf", message: "DXF export is generated on demand from the current layout result." },
            { kind: "pdf", label: "PDF report", status: "available", url: "/v1/nesting/jobs/job-1/artifact/pdf", message: "PDF report is generated on demand from the current job summary." },
          ],
        economics: {
          status: "available",
          material_cost: 120,
          used_material_cost: 102,
          waste_cost: 18,
          savings_percent: 10,
          currency: "USD",
          cost_basis: "per_sheet",
          material_cost_estimated: false,
          used_material_cost_estimated: true,
          waste_cost_estimated: true,
          savings_percent_estimated: true,
          message: "Total sheet spend uses the configured per-sheet cost. Used, waste, and recoverable savings values are area-based estimates.",
        },
        offcuts: [
          {
            sheet_id: "sheet-1",
            instance: 1,
            area: 10,
            approx_shape: "rectangle",
            bounds: { min_x: 85, min_y: 0, max_x: 100, max_y: 10, width: 15, height: 10 },
            reusable: true,
            approximation: true,
            source: "right_strip",
          },
        ],
      offcut_summary: {
        total_leftover_area: 15,
        reusable_leftover_area: 10,
        reusable_area_estimate: 10,
        estimated_scrap_area: 5,
        reusable_piece_count: 1,
        approximation: true,
        approximation_method: "bounding_box_strips",
        message:
          "Reusable leftovers are approximated as rectangular strips outside the placed-parts bounding box. Internal gaps remain estimated scrap until polygonal recovery is added.",
        leftover_summaries: [
          {
            sheet_id: "sheet-1",
            instance: 1,
            width: 5,
            height: 2,
            area: 10,
            approximate: true,
            source: "right_strip",
          },
        ],
        sheets: [
          {
            sheet_id: "sheet-1",
            instance: 1,
              sheet_area: 100,
              used_area: 85,
              scrap_area: 15,
              reusable_leftover_area: 10,
              estimated_scrap_area: 5,
              reusable_piece_count: 1,
              approximation: true,
              approximation_method: "bounding_box_strips",
              message:
                "Reusable leftovers are approximated as rectangular strips outside the placed-parts bounding box. Internal gaps remain estimated scrap until polygonal recovery is added.",
            },
          ],
        },
        unplaced_parts: [],
        parts: [
          {
            part_id: "part-1",
            filename: "part-a.dxf",
            requested_quantity: 1,
            placed_quantity: 4,
            remaining_quantity: 0,
            area_contribution: 85,
            order_id: "order-a",
            order_name: "Order A",
            priority: 2,
          },
        ],
        batch: {
          batch_id: "batch-alpha",
          batch_name: "Batch Alpha",
          orders: [{ order_id: "order-a", order_name: "Order A", priority: 2, part_ids: ["part-1"] }],
        },
        run_number: 1,
        compute_time_sec: 12.4,
        improvement_percent: 0,
      });
    }
    return jsonResponse({});
  }) as ReturnType<typeof vi.fn> & { getCreateJobPayload: () => unknown };
  fetchMock.getCreateJobPayload = () => createJobPayload;
  return fetchMock;
}

function renderWorkspace() {
  window.location.hash = "/workspace";
  return render(<App />);
}

async function moveToScreenTwo(user: ReturnType<typeof userEvent.setup>, language: AppLanguage) {
  const t = (key: string, params?: Record<string, string | number>) => translate(language, key, params);
  await user.upload(screen.getByLabelText(t("upload.dxfFile")), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
  await user.click(await screen.findByRole("button", { name: t("common.next") }));
  await screen.findByLabelText(t("nesting.materialName"));
}

describe("App 3-screen workflow", () => {
  beforeEach(() => {
    window.location.hash = "/workspace";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.location.hash = "";
    window.localStorage.clear();
  });

  it("validates uploaded files automatically when Screen 1 Next is pressed", async () => {
    const fetchMock = buildFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));

    expect(await screen.findByText("Material & Parameters")).toBeInTheDocument();
    expect(screen.getByText("part-a.dxf")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/v1/geometry/clean"))).toBe(true);
  });

  it("stays on Screen 1 and shows clear errors when validation fails", async () => {
    vi.stubGlobal("fetch", buildFetchMock({ importPolygons: 0, cleanPolygons: 0 }));

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "broken.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));

    expect(await screen.findByText("Validation failed. Review the file issues below.")).toBeInTheDocument();
    expect(screen.getByText(/broken\.dxf: Import produced no valid polygons\./i)).toBeInTheDocument();
    expect(screen.getByText("Validation Gate")).toBeInTheDocument();
  });

  it("preserves uploaded files and parameter values while navigating back and next", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));

    const materialName = await screen.findByLabelText("Material name");
    await user.type(materialName, "Steel S235");
    await user.clear(screen.getByLabelText("Thickness"));
    await user.type(screen.getByLabelText("Thickness"), "3");
    await user.click(screen.getAllByRole("button", { name: "Next" })[0]);

    expect(await screen.findByText("Run Control")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByLabelText("Material name")).toHaveValue("Steel S235");
    expect(screen.getByLabelText("Thickness")).toHaveValue(3);

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByText("part-a.dxf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
  });

  it("loads a saved material preset, persists selection, and includes material in the job payload", async () => {
    const fetchMock = buildFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));
    await user.type(screen.getByPlaceholderText("Order ID"), "order-a");
    await user.type(screen.getByPlaceholderText("Order name"), "Order A");
    await user.type(screen.getByPlaceholderText("Priority"), "2");

    await user.selectOptions(await screen.findByLabelText("Material preset"), "preset-mild-steel-3mm");
    expect(await screen.findByLabelText("Material name")).toHaveValue("Mild Steel 3 mm");
    expect(screen.getByLabelText("Sheet width")).toHaveValue(3000);
    expect(window.localStorage.getItem("nestora-selected-material-id")).toBe("preset-mild-steel-3mm");

    await user.click(screen.getAllByRole("button", { name: "Next" })[0]);
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    await waitFor(() => expect(fetchMock.getCreateJobPayload()).not.toBeNull());
    expect(fetchMock.getCreateJobPayload()).toMatchObject({
      material: {
        material_id: "preset-mild-steel-3mm",
        name: "Mild Steel 3 mm",
        sheet_width: 3000,
        sheet_height: 1500,
        units: "mm",
        kerf: 2,
        cost_per_sheet: 120,
        currency: "USD",
      },
      batch: {
        batch_id: "batch-current",
        batch_name: "Current batch",
        orders: [{ order_id: "order-a", order_name: "Order A", priority: 2, part_ids: ["part-1"] }],
      },
      parts: [{ order_id: "order-a", order_name: "Order A", priority: 2 }],
    });
  });

  it("restores the last selected material preset after reload", async () => {
    window.localStorage.setItem("nestora-selected-material-id", "preset-mild-steel-3mm");
    vi.stubGlobal("fetch", buildFetchMock());

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));

    expect(await screen.findByLabelText("Material preset")).toHaveValue("preset-mild-steel-3mm");
    expect(screen.getByLabelText("Material name")).toHaveValue("Mild Steel 3 mm");
    expect(screen.getByLabelText("Sheet width")).toHaveValue(3000);
  });

  it("groups multiple explicit orders into one batch payload and shows them in the UI", async () => {
    const fetchMock = buildFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(
      screen.getByLabelText("DXF file"),
      [
        new File(["a"], "part-a.dxf", { type: "application/dxf" }),
        new File(["b"], "part-b.dxf", { type: "application/dxf" }),
      ],
    );
    await user.click(await screen.findByRole("button", { name: "Next" }));

    const orderIdInputs = screen.getAllByLabelText("Order ID");
    const orderNameInputs = screen.getAllByLabelText("Order name");
    const priorityInputs = screen.getAllByLabelText("Priority");

    await user.type(orderIdInputs[0], "order-a");
    await user.type(orderNameInputs[0], "Order A");
    await user.type(priorityInputs[0], "2");
    await user.type(orderIdInputs[1], "order-b");
    await user.type(orderNameInputs[1], "Order B");
    await user.type(priorityInputs[1], "1");

    expect(screen.getByText("Batch grouping")).toBeInTheDocument();
    expect(screen.getByText("Order A")).toBeInTheDocument();
    expect(screen.getByText("Order B")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Next" })[0]);
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    await waitFor(() => expect(fetchMock.getCreateJobPayload()).not.toBeNull());
    expect(fetchMock.getCreateJobPayload()).toMatchObject({
      batch: {
        orders: [
          { order_id: "order-a", order_name: "Order A", priority: 2, part_ids: ["part-1"] },
          { order_id: "order-b", order_name: "Order B", priority: 1, part_ids: ["part-2"] },
        ],
      },
      parts: [
        { order_id: "order-a", order_name: "Order A", priority: 2 },
        { order_id: "order-b", order_name: "Order B", priority: 1 },
      ],
    });
  });

  it("applies one order grouping to multiple selected parts from the screen 2 batch editor", async () => {
    const fetchMock = buildFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(
      screen.getByLabelText("DXF file"),
      [
        new File(["a"], "part-a.dxf", { type: "application/dxf" }),
        new File(["b"], "part-b.dxf", { type: "application/dxf" }),
      ],
    );
    await user.click(await screen.findByRole("button", { name: "Next" }));

    await user.clear(screen.getByLabelText("Batch order ID"));
    await user.type(screen.getByLabelText("Batch order ID"), "order-z");
    await user.type(screen.getByLabelText("Batch order name"), "Order Z");
    await user.type(screen.getByLabelText("Batch priority"), "7");
    await user.click(screen.getByRole("button", { name: "Apply to selected parts" }));

    const orderIdInputs = screen.getAllByLabelText("Order ID");
    const orderNameInputs = screen.getAllByLabelText("Order name");
    const priorityInputs = screen.getAllByLabelText("Priority");
    expect(orderIdInputs[0]).toHaveValue("order-z");
    expect(orderIdInputs[1]).toHaveValue("order-z");
    expect(orderNameInputs[0]).toHaveValue("Order Z");
    expect(orderNameInputs[1]).toHaveValue("Order Z");
    expect(priorityInputs[0]).toHaveValue(7);
    expect(priorityInputs[1]).toHaveValue(7);

    await user.click(screen.getAllByRole("button", { name: "Next" })[0]);
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    await waitFor(() => expect(fetchMock.getCreateJobPayload()).not.toBeNull());
    expect(fetchMock.getCreateJobPayload()).toMatchObject({
      batch: {
        orders: [{ order_id: "order-z", order_name: "Order Z", priority: 7 }],
      },
      parts: [
        { order_id: "order-z", order_name: "Order Z", priority: 7 },
        { order_id: "order-z", order_name: "Order Z", priority: 7 },
      ],
    });
  });

  it("runs from Screen 3 and shows result metrics with repeat action visible", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));

    await user.type(await screen.findByLabelText("Material name"), "Steel");
    await user.click(screen.getAllByRole("button", { name: "Next" })[0]);
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    await waitFor(() => expect(screen.getByText("Result Metrics")).toBeInTheDocument());
    expect(screen.getByText("Batch Overview")).toBeInTheDocument();
    expect(screen.getByText("Batch Alpha")).toBeInTheDocument();
    expect(screen.getByText("Per-Part Results")).toBeInTheDocument();
    expect(screen.getByText("Batch Orders")).toBeInTheDocument();
    expect(screen.getByText("Order A")).toBeInTheDocument();
    expect(screen.getByText("Artifacts")).toBeInTheDocument();
    expect(screen.getByText("Offcut Summary")).toBeInTheDocument();
    expect(screen.getByText("Approximation")).toBeInTheDocument();
    expect(screen.getByText("Reusable Leftover")).toBeInTheDocument();
    expect(screen.getByText("Estimated Scrap Remainder")).toBeInTheDocument();
    expect(screen.getByText("Material Cost")).toBeInTheDocument();
    expect(screen.getByText("Used Material Cost")).toBeInTheDocument();
    expect(screen.getByText("Waste Cost")).toBeInTheDocument();
    expect(screen.getByText("Savings Percent")).toBeInTheDocument();
    expect(screen.getByText("102.00 USD (estimated)")).toBeInTheDocument();
    expect(screen.getByText("18.00 USD (estimated)")).toBeInTheDocument();
    expect(screen.getByText("10.0% (estimated)")).toBeInTheDocument();
    expect(screen.getByText(/per-sheet cost/i)).toBeInTheDocument();
    expect(screen.getByText(/Internal gaps remain estimated scrap/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Repeat" }).length).toBeGreaterThan(0);
  });

  it("renders truthful artifact states on Screen 3 when exports are not all downloadable", async () => {
    vi.stubGlobal(
      "fetch",
      buildFetchMock({
        resultArtifacts: [
          { kind: "json", label: "JSON result", status: "available", url: "/v1/nesting/jobs/job-1/artifact", message: "JSON result is ready to download from the current job." },
          { kind: "dxf", label: "DXF layout", status: "processing", message: "DXF export will be available after the nesting job finishes." },
          { kind: "pdf", label: "PDF report", status: "failed", message: "PDF export failed: renderer unavailable" },
        ],
      }),
    );

    renderWorkspace();
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("DXF file"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Next" }));
    await user.type(await screen.findByLabelText("Material name"), "Steel");
    await user.click(screen.getAllByRole("button", { name: "Next" })[0]);
    await user.click(await screen.findByRole("button", { name: "Run Nesting" }));

    expect(await screen.findByText("Artifacts")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("DXF export will be available after the nesting job finishes.")).toBeInTheDocument();
    expect(screen.getByText("PDF export failed: renderer unavailable")).toBeInTheDocument();
  });

  it("applies the selected language across the 3-screen workspace flow and persists it", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    renderWorkspace();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "tr");
    expect(window.localStorage.getItem("nestora-language")).toBe("tr");
    expect(screen.getByRole("button", { name: "DXF Dosyasi Sec" })).toBeInTheDocument();

    await user.upload(screen.getByLabelText("DXF dosyasi"), new File(["a"], "part-a.dxf", { type: "application/dxf" }));
    await user.click(await screen.findByRole("button", { name: "Ileri" }));

    expect(await screen.findByLabelText("Malzeme adi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Geri" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ileri" }).length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText("Malzeme adi"), "Steel");
    await user.click(screen.getAllByRole("button", { name: "Ileri" })[0]);

    expect(await screen.findByText("Calistirma Kontrolu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tekrarla" })).toBeInTheDocument();
    expect(screen.getByText("Ciktilar")).toBeInTheDocument();
  });

  it("restores the selected language after refresh", async () => {
    vi.stubGlobal("fetch", buildFetchMock());

    const user = userEvent.setup();
    const view = renderWorkspace();

    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "tr");
    expect(window.localStorage.getItem("nestora-language")).toBe("tr");

    view.unmount();
    renderWorkspace();

    expect(screen.getByRole("combobox", { name: "Dil" })).toHaveValue("tr");
    expect(screen.getByRole("button", { name: "DXF Dosyasi Sec" })).toBeInTheDocument();
  });

  it("renders localized core labels on screens 1-3 for each supported language", async () => {
    const snapshots: Record<string, unknown> = {};

    for (const language of ["en", "tr", "uk"] as AppLanguage[]) {
      cleanup();
      window.localStorage.clear();
      vi.stubGlobal("fetch", buildFetchMock());

      const t = (key: string, params?: Record<string, string | number>) => translate(language, key, params);
      const user = userEvent.setup();
      renderWorkspace();

      await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), language);
      const screen1 = {
        upload: screen.getByRole("button", { name: t("upload.select") }).textContent,
        next: screen.getByRole("button", { name: t("common.next") }).textContent,
        validation: screen.getByText(t("screen1.validationGate")).textContent,
      };

      await moveToScreenTwo(user, language);

      const screen2State = {
        materialName: t("nesting.materialName"),
        back: screen.getByRole("button", { name: t("common.back") }).textContent,
        next: screen.getAllByRole("button", { name: t("common.next") })[0].textContent,
      };

      await user.type(screen.getByLabelText(t("nesting.materialName")), "Steel");
      await user.click(screen.getAllByRole("button", { name: t("common.next") })[0]);
      await screen.findByText(t("screen3.runControl"));

      snapshots[language] = {
        screen1,
        screen2: screen2State,
        screen3: {
          runControl: screen.getByText(t("screen3.runControl")).textContent,
          runAction: screen.getByRole("button", { name: t("screen3.runNesting") }).textContent,
          repeat: screen.getByRole("button", { name: t("common.repeat") }).textContent,
          artifacts: screen.getByText(t("screen3.artifacts")).textContent,
          resultMetrics: screen.getByText(t("metrics.title")).textContent,
        },
      };
    }

    expect(snapshots).toMatchInlineSnapshot(`
      {
        "en": {
          "screen1": {
            "next": "Next",
            "upload": "Select DXF File(s)",
            "validation": "Validation Gate",
          },
          "screen2": {
            "back": "Back",
            "materialName": "Material name",
            "next": "Next",
          },
          "screen3": {
            "artifacts": "Artifacts",
            "repeat": "Repeat",
            "resultMetrics": "Result Metrics",
            "runAction": "Run Nesting",
            "runControl": "Run Control",
          },
        },
        "tr": {
          "screen1": {
            "next": "Ileri",
            "upload": "DXF Dosyasi Sec",
            "validation": "Dogrulama Gecidi",
          },
          "screen2": {
            "back": "Geri",
            "materialName": "Malzeme adi",
            "next": "Ileri",
          },
          "screen3": {
            "artifacts": "Ciktilar",
            "repeat": "Tekrarla",
            "resultMetrics": "Sonuc Metrikleri",
            "runAction": "Nesting Calistir",
            "runControl": "Calistirma Kontrolu",
          },
        },
        "uk": {
          "screen1": {
            "next": "Dali",
            "upload": "Obraty DXF Fail(y)",
            "validation": "Barier Validatsii",
          },
          "screen2": {
            "back": "Nazad",
            "materialName": "Nazva materialu",
            "next": "Dali",
          },
          "screen3": {
            "artifacts": "Artefakty",
            "repeat": "Povtoryty",
            "resultMetrics": "Metryky Resultatu",
            "runAction": "Zapustyty Nesting",
            "runControl": "Keruvannya Zapuskom",
          },
        },
      }
    `);
  });
});
