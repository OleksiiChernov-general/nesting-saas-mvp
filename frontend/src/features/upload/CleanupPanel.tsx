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
        className="w-full rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-accent hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-500"
        disabled={!importResult || importResult.polygons.length === 0 || loading}
        onClick={onClean}
        type="button"
      >
        {loading ? "Cleaning..." : "Clean Geometry"}
      </button>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3">
          <div className="text-slate-500">Valid polygons</div>
          <div className="mt-1 font-semibold text-slate-100">{validPolygonCount}</div>
        </div>
        <div className="rounded-2xl border border-[color:var(--border)] bg-black/15 px-4 py-3">
          <div className="text-slate-500">Invalid shapes</div>
          <div className="mt-1 font-semibold text-slate-100">{invalidShapeCount}</div>
        </div>
      </div>
      {cleanupResult ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-white/[0.03] px-4 py-3 text-sm text-slate-300">
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
