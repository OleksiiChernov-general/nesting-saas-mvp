# Frontend MVP

React + TypeScript + Vite frontend for the multi-part Nesting SaaS MVP workflow.

## Current workflow

Implemented now:

1. Upload multiple DXF files.
2. Run cleanup across all uploaded parts.
3. Configure part list.
4. Choose `Fill Sheet` or `Batch Quantity`.
5. Submit the new request contract.
6. Poll job status.
7. Read the new result contract with per-part counts.

Temporarily simplified:

- The UI already behaves like a multi-part production tool.
- The backend algorithm is greedy rather than globally optimal.
- Result counts are authoritative even when a more advanced solver could produce a tighter packing.

Deferred to the next algorithm iteration:

- Maximize-fill heuristics
- Batch packing optimality
- More complex placement strategy

## Prerequisites

- Node.js 20+
- npm 10+
- Running Nesting SaaS MVP backend on a reachable URL

## Installation

```powershell
cd "C:\Users\Aleksey.Chernov\Desktop\Бюджет закупок\CSV_Export\nesting_saas_mvp\frontend"
npm install
```

## Environment setup

Copy `.env.example` to `.env` if you need a custom backend URL:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Notes:

- If `VITE_API_BASE_URL` is missing, the app falls back to the current browser origin.
- Keep the backend URL in environment config only. Do not hardcode it in source files.

## Run in development

```powershell
npm run dev
```

## Run tests

```powershell
npm run test
```

## Build

```powershell
npm run build
```

## Backend requirement

The frontend expects these backend endpoints to be available:

- `GET /health`
- `POST /v1/files/import`
- `POST /v1/geometry/clean`
- `POST /v1/nesting/jobs`
- `GET /v1/nesting/jobs/{id}`
- `GET /v1/nesting/jobs/{id}/result`

## Workflow

1. Upload one or more DXF files.
2. Run geometry cleanup.
3. Review the multi-part list and remove/disable parts if needed.
4. Choose `Fill Sheet` or `Batch Quantity`.
5. In `Batch Quantity`, enter requested quantity for each enabled part.
6. Configure sheet size, quantity, units, gap, and objective.
7. Start nesting and wait for polling to finish.
8. Inspect per-part counts, mode used, layouts, and metrics.

## File structure

```text
frontend/
  src/
    api/
    app/
    components/
    features/
      metrics/
      nesting/
      status/
      upload/
      viewer/
    test/
    types/
    utils/
  .env.example
  index.html
  package.json
  postcss.config.cjs
  tailwind.config.ts
  tsconfig.app.json
  tsconfig.json
  tsconfig.node.json
  vite.config.ts
```

## Troubleshooting

- `npm install` fails: confirm Node.js 20+ and npm 10+ are installed.
- The UI shows `Disconnected`: start the backend and verify `VITE_API_BASE_URL`.
- Upload works but nesting never completes: check that the backend worker and Redis queue are running.
- Tests fail in a clean checkout: run `npm install` again to ensure Vitest and Testing Library are installed.
- Viewer looks empty after success: check whether the result contains empty layouts or all parts were unplaced.

## URLs

- Backend URL: `http://localhost:8000`
- Frontend URL: `http://localhost:5173`
