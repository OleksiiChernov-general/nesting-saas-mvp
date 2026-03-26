import { useEffect, useMemo, useState } from "react";

import { Panel } from "../../components/Panel";
import type { NestingDebugResponse, PolygonPayload, SheetLayoutResponse } from "../../types/api";
import { buildPolygonPath, createViewBox, getPreviewBounds } from "../../utils/viewer";
import { SheetNavigator } from "./SheetNavigator";

type LayoutViewerProps = {
  layouts: SheetLayoutResponse[];
  debug: NestingDebugResponse | null;
  previewPolygons: PolygonPayload[];
  activeSheetIndex: number;
  onSheetChange: (nextIndex: number) => void;
  canShowResult: boolean;
};

const palette = ["#0f766e", "#2563eb", "#ca8a04", "#7c3aed", "#dc2626", "#0891b2"];

function sanitizePolygons(polygons: PolygonPayload[]): PolygonPayload[] {
  return polygons.filter((polygon) => polygon.points.length >= 4);
}

function safePartLabel(partId: string | undefined, index: number): string {
  return partId && partId.trim() ? partId : `part-${index + 1}`;
}

export function LayoutViewer({
  layouts,
  debug,
  previewPolygons,
  activeSheetIndex,
  onSheetChange,
  canShowResult,
}: LayoutViewerProps) {
  const safeLayouts = useMemo(
    () =>
      layouts.map((layout, layoutIndex) => ({
        ...layout,
        sheet_id: layout.sheet_id || `sheet-${layoutIndex + 1}`,
        placements: layout.placements.filter((placement) => placement.polygon?.points?.length >= 4),
        width: layout.width > 0 ? layout.width : 1,
        height: layout.height > 0 ? layout.height : 1,
      })),
    [layouts],
  );
  const safePreviewPolygons = useMemo(() => sanitizePolygons(previewPolygons), [previewPolygons]);
  const activeLayout = safeLayouts[activeSheetIndex] ?? null;
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selectedPartId, setSelectedPartId] = useState<string | null>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);

  const previewBounds = useMemo(
    () => getPreviewBounds(canShowResult ? activeLayout : null, canShowResult ? [] : safePreviewPolygons),
    [activeLayout, canShowResult, safePreviewPolygons],
  );
  const viewBox = useMemo(() => createViewBox(previewBounds), [previewBounds]);
  const flipYAxis = previewBounds.minY + previewBounds.maxY;
  const activeDebugSheet = debug?.sheets[activeSheetIndex] ?? null;
  const activeDebugPlacements = useMemo(
    () =>
      activeDebugSheet
        ? debug?.placements.filter(
            (placement) =>
              placement.sheet_id === activeDebugSheet.sheet_id && placement.instance === activeDebugSheet.instance,
          ) ?? []
        : [],
    [activeDebugSheet, debug?.placements],
  );

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setSelectedPartId(null);
  }, [activeSheetIndex, activeLayout, safePreviewPolygons, canShowResult]);

  return (
    <Panel
      title="Layout Viewer"
      subtitle={canShowResult && activeLayout ? "Nested layout preview" : "Geometry preview"}
      actions={
        <div className="flex items-center gap-3">
          <SheetNavigator
            current={activeSheetIndex}
            onNext={() => onSheetChange(Math.min(activeSheetIndex + 1, safeLayouts.length - 1))}
            onPrevious={() => onSheetChange(Math.max(activeSheetIndex - 1, 0))}
            total={safeLayouts.length}
          />
          <div className="flex items-center gap-2">
            <button className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700" onClick={() => setZoom((value) => Math.min(value * 1.2, 6))} type="button">+</button>
            <button className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700" onClick={() => setZoom((value) => Math.max(value / 1.2, 0.5))} type="button">-</button>
            <button
              className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700"
              onClick={() => {
                setZoom(1);
                setPan({ x: 0, y: 0 });
              }}
              type="button"
            >
              Zoom to fit
            </button>
          </div>
        </div>
      }
    >
      <div className="rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(135deg,#f8fafc_0%,#eef2f7_100%)] p-4">
        <svg
          className="h-[540px] w-full cursor-grab rounded-[1.25rem] bg-slate-50"
          onMouseDown={(event) => setDragStart({ x: event.clientX, y: event.clientY })}
          onMouseLeave={() => setDragStart(null)}
          onMouseMove={(event) => {
            if (!dragStart) return;
            setPan((current) => ({
              x: current.x + (event.clientX - dragStart.x) * 0.6,
              y: current.y + (event.clientY - dragStart.y) * 0.6,
            }));
            setDragStart({ x: event.clientX, y: event.clientY });
          }}
          onMouseUp={() => setDragStart(null)}
          preserveAspectRatio="xMidYMid meet"
          viewBox={viewBox}
        >
          <defs>
            <pattern height="12" id="grid" patternUnits="userSpaceOnUse" width="12">
              <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#d9e1e8" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect fill="url(#grid)" height="100%" width="100%" x="-10000" y="-10000" />
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {canShowResult && activeLayout ? (
              <>
                <rect fill="#ffffff" height={activeLayout.height} rx={2} stroke="#1e293b" strokeWidth="1.5" width={activeLayout.width} x={0} y={0} />
                {activeLayout.placements.length === 0 ? (
                  <text fill="#64748b" fontSize="5" x={activeLayout.width / 2 - 18} y={activeLayout.height / 2}>
                    No parts placed on this sheet.
                  </text>
                ) : null}
                <g transform={`translate(0 ${flipYAxis}) scale(1 -1)`}>
                  {activeLayout.placements.map((placement, index) => {
                    const active = selectedPartId === placement.part_id;
                    const label = safePartLabel(placement.part_id, index);
                    return (
                      <path
                        d={buildPolygonPath(placement.polygon)}
                        fill={`${palette[index % palette.length]}33`}
                        key={`${label}-${placement.instance}-${index}-shape`}
                        onClick={() => setSelectedPartId(label)}
                        stroke={active ? "#0f172a" : palette[index % palette.length]}
                        strokeWidth={active ? 2.4 : 1.25}
                      />
                    );
                  })}
                </g>
                {activeDebugPlacements.map((placement) => (
                  <rect
                    fill="none"
                    height={placement.bbox.height}
                    key={`${placement.placement_id}-bbox`}
                    stroke="#ef4444"
                    strokeDasharray="2 2"
                    strokeWidth="0.8"
                    width={placement.bbox.width}
                    x={placement.bbox.min_x}
                    y={flipYAxis - placement.bbox.max_y}
                  />
                ))}
                {activeLayout.placements.map((placement, index) => {
                  const label = safePartLabel(placement.part_id, index);
                  return (
                    <text
                      fill="#0f172a"
                      fontFamily="IBM Plex Mono, monospace"
                      fontSize="5"
                      key={`${label}-${placement.instance}-${index}-label`}
                      x={placement.x + placement.width / 2}
                      y={flipYAxis - (placement.y + placement.height / 2)}
                    >
                      {label}
                    </text>
                  );
                })}
              </>
            ) : safePreviewPolygons.length ? (
              <g transform={`translate(0 ${flipYAxis}) scale(1 -1)`}>
                {safePreviewPolygons.map((polygon, index) => (
                  <path
                    d={buildPolygonPath(polygon)}
                    fill={`${palette[index % palette.length]}22`}
                    key={`preview-${index}`}
                    stroke={palette[index % palette.length]}
                    strokeWidth="1.25"
                  />
                ))}
              </g>
            ) : (
              <text fill="#64748b" fontSize="8" x="10" y="20">
                Upload and process a DXF to see geometry here.
              </text>
            )}
          </g>
        </svg>
      </div>
      {debug?.warnings.length ? (
        <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {debug.warnings.join(" ")}
        </div>
      ) : null}
    </Panel>
  );
}
