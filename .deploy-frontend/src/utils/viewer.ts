import type { Point, PolygonPayload, SheetLayoutResponse } from "../types/api";

type Bounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

function boundsFromPoints(points: Point[]): Bounds {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

export function buildPolygonPath(polygon: PolygonPayload): string {
  if (!polygon.points.length) return "";
  return polygon.points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ") + " Z";
}

export function getPreviewBounds(layout: SheetLayoutResponse | null, polygons: PolygonPayload[]): Bounds {
  if (layout) {
    return { minX: 0, minY: 0, maxX: layout.width, maxY: layout.height };
  }

  if (polygons.length === 0) {
    return { minX: 0, minY: 0, maxX: 100, maxY: 100 };
  }

  return polygons
    .map((polygon) => boundsFromPoints(polygon.points))
    .reduce<Bounds>(
      (accumulator, item) => ({
        minX: Math.min(accumulator.minX, item.minX),
        minY: Math.min(accumulator.minY, item.minY),
        maxX: Math.max(accumulator.maxX, item.maxX),
        maxY: Math.max(accumulator.maxY, item.maxY),
      }),
      {
        minX: Number.POSITIVE_INFINITY,
        minY: Number.POSITIVE_INFINITY,
        maxX: Number.NEGATIVE_INFINITY,
        maxY: Number.NEGATIVE_INFINITY,
      },
    );
}

export function createViewBox(bounds: Bounds): string {
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const margin = Math.max(width, height) * 0.08;
  return `${bounds.minX - margin} ${bounds.minY - margin} ${width + margin * 2} ${height + margin * 2}`;
}
