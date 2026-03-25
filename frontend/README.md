# Frontend MVP

React + TypeScript + Vite frontend for the Nesting SaaS MVP backend.

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

1. Upload a DXF file.
2. Run geometry cleanup.
3. Configure sheet size, quantity, gap, and objective.
4. Start nesting.
5. Wait for polling to finish.
6. Inspect layout and metrics.

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
