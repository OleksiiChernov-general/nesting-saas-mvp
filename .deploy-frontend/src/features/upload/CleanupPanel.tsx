import type { CleanGeometryResponse, ImportResponse } from "../../types/api";
import { Panel } from "../../components/Panel";
import { StatusMessage } from "../../components/StatusMessage";

type CleanupPanelProps = {
  importResult: ImportResponse | null;
  cleanupResult: CleanGeometryResponse | null;
  loading: boolean;
  error: string | null;
  statusMessage: string;
  onClean: () => void;
};

export function CleanupPanel({ importResult, cleanupResult, loading, error, statusMessage, onClean }: CleanupPanelProps) {
  const validPolygonCount = cleanupResult?.polygons.length ?? 0;
  const invalidShapeCount = cleanupResult?.invalid_shapes.length ?? importResult?.invalid_shapes.length ?? 0;

  return (
    <Panel title="Geometry Cleanup" subtitle="Repair and validate geometry before nesting.">
      <button
        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-900 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
        disabled={!importResult || importResult.polygons.length === 0 || loading}
        onClick={onClean}
        type="button"
      >
        {loading ? "Cleaning..." : "Clean Geometry"}
      </button>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-2xl bg-slate-100 px-4 py-3">
          <div className="text-slate-500">Valid polygons</div>
          <div className="mt-1 font-semibold text-slate-900">{validPolygonCount}</div>
        </div>
        <div className="rounded-2xl bg-slate-100 px-4 py-3">
          <div className="text-slate-500">Invalid shapes</div>
          <div className="mt-1 font-semibold text-slate-900">{invalidShapeCount}</div>
        </div>
      </div>
      {cleanupResult ? (
        <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
          Removed during cleanup: {cleanupResult.removed}
          {cleanupResult.invalid_shapes.length > 0 ? `, warnings: ${cleanupResult.invalid_shapes.length}` : ", warnings: 0"}
        </div>
      ) : null}
      <StatusMessage
        message={statusMessage}
        tone={error ? "error" : cleanupResult ? "success" : !importResult ? "warning" : "neutral"}
      />
      {error ? <StatusMessage message={error} tone="error" /> : null}
    </Panel>
  );
}
