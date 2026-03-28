# Nesting SaaS MVP

Backend + frontend MVP for a multi-part nesting workflow with DXF import, per-part configuration, async job execution, and per-part result reporting.

## Current status

Implemented now:

- Multi-file upload flow
- Per-part cleanup and primary-polygon selection
- Explicit mode selection: `fill_sheet` and `batch_quantity`
- Per-part job configuration with enable/disable, fill-only, and requested quantity
- New request contract built around `mode`, `parts`, and `sheet`
- New result contract built around `mode`, `summary`, and `parts`
- Job polling/status payload aligned with the same multi-part model
- Real Fill Sheet behavior that keeps placing copies until no enabled part fits
- Real Batch Quantity behavior that keeps placing requested parts until all are placed or no more fit
- Mixed multi-part placement on the same sheet
- Backend, frontend, and integration tests for the new workflow

Root cause of the old under-placement behavior:

- The previous nesting loop was effectively `first-fit`.
- It accepted the first feasible placement found for the first feasible part.
- Candidate search was too shallow, so the engine could stop after a trivial early placement pattern even when more placements fit.
- That especially hurt Fill Sheet mode and mixed-part jobs.

Current heuristic:

- Enumerate feasible placements for each enabled part and rotation.
- Score placements greedily instead of taking the first valid one.
- Use a one-step lookahead bonus so the next choice prefers placements that still leave room for another productive part afterwards.
- In `fill_sheet`, prioritize high area usage with compact placements that keep packing pressure on the sheet and avoid trivial single-type early choices when a mixed continuation fits.
- In `batch_quantity`, prioritize outstanding requested area while still preferring compact valid placements that preserve feasible follow-up demand.
- Stop only when no enabled part can fit anymore, or when all batch quantities are satisfied.

Deferred to the next algorithm iteration:

- Maximize-fill heuristics
- Batch packing optimality
- Complex placement strategy and smarter search

## Request contract

Primary job request:

```json
{
  "mode": "batch_quantity",
  "parts": [
    {
      "part_id": "part-a",
      "filename": "part-a.dxf",
      "quantity": 10,
      "enabled": true,
      "fill_only": false,
      "polygon": {
        "points": [{"x": 0, "y": 0}, {"x": 40, "y": 0}, {"x": 40, "y": 20}, {"x": 0, "y": 20}, {"x": 0, "y": 0}]
      }
    }
  ],
  "sheet": {
    "sheet_id": "sheet-1",
    "width": 100,
    "height": 100,
    "quantity": 1,
    "units": "mm"
  },
  "params": {
    "gap": 2.0,
    "rotation": [0, 180],
    "objective": "maximize_yield"
  }
}
```

## Response contract

Primary result shape:

```json
{
  "mode": "batch_quantity",
  "summary": {
    "total_parts": 3
  },
  "parts": [
    {
      "part_id": "part-a",
      "filename": "part-a.dxf",
      "requested_quantity": 10,
      "placed_quantity": 1,
      "remaining_quantity": 9
    }
  ],
  "total_parts_placed": 1
}
```

## File tree

```text
nesting_saas_mvp/
  app/
    api.py
    db.py
    dxf_parser.py
    geometry.py
    main.py
    models.py
    nesting.py
    queue.py
    schemas.py
    services.py
    settings.py
    storage.py
    worker.py
  tests/
    conftest.py
    test_api.py
    test_dxf_parser.py
    test_geometry.py
    test_jobs.py
    test_nesting.py
  Dockerfile
  docker-compose.yml
  pytest.ini
  requirements.txt
```

## Prerequisites

- Docker Desktop with Compose
- Optional for local non-Docker runs: Python 3.11

## Run with Docker

From this directory:

```powershell
docker compose up --build
```

Detached mode:

```powershell
docker compose up --build -d
```

Services:

- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Health check:

```powershell
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Useful checks:

```powershell
docker compose ps
docker compose logs api
docker compose logs worker
```

Stop the stack:

```powershell
docker compose down
```

## Run tests

Local Python:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

Inside Docker API image:

```powershell
docker compose run --rm api pytest
```

## Sample API flow

### Mixed Fill Sheet example

```json
{
  "mode": "fill_sheet",
  "parts": [
    {
      "part_id": "large",
      "filename": "large.dxf",
      "enabled": true,
      "polygon": {
        "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}, {"x": 0, "y": 0}]
      }
    },
    {
      "part_id": "small",
      "filename": "small.dxf",
      "enabled": true,
      "polygon": {
        "points": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 10}, {"x": 0, "y": 10}, {"x": 0, "y": 0}]
      }
    }
  ],
  "sheet": { "sheet_id": "sheet-1", "width": 25, "height": 10, "quantity": 1, "units": "mm" },
  "params": { "gap": 0, "rotation": [0, 90, 180, 270], "objective": "maximize_yield" }
}
```

Expected behavior: 2 `large` + 1 `small` on one sheet, with a clearly mixed result.

### Mixed Batch Quantity example

```json
{
  "mode": "batch_quantity",
  "parts": [
    {
      "part_id": "large",
      "filename": "large.dxf",
      "enabled": true,
      "quantity": 1,
      "polygon": {
        "points": [{"x": 0, "y": 0}, {"x": 12, "y": 0}, {"x": 12, "y": 10}, {"x": 0, "y": 10}, {"x": 0, "y": 0}]
      }
    },
    {
      "part_id": "small",
      "filename": "small.dxf",
      "enabled": true,
      "quantity": 4,
      "polygon": {
        "points": [{"x": 0, "y": 0}, {"x": 8, "y": 0}, {"x": 8, "y": 10}, {"x": 0, "y": 10}, {"x": 0, "y": 0}]
      }
    }
  ],
  "sheet": { "sheet_id": "sheet-1", "width": 20, "height": 20, "quantity": 1, "units": "mm" },
  "params": { "gap": 0, "rotation": [0, 90, 180, 270], "objective": "maximize_yield" }
}
```

Expected behavior: place the large part and as many requested small parts as fit, returning per-part `placed_quantity`, `remaining_quantity`, and `area_contribution`.

### 1. Import DXF

```powershell
curl -X POST http://localhost:8000/v1/files/import `
  -F "file=@sample.dxf"
```

### 2. Clean geometry

```powershell
curl -X POST http://localhost:8000/v1/geometry/clean `
  -H "Content-Type: application/json" `
  -d '{
    "polygons": [
      {
        "points": [
          {"x": 0, "y": 0},
          {"x": 40, "y": 0},
          {"x": 40, "y": 20},
          {"x": 0, "y": 20},
          {"x": 0, "y": 0}
        ]
      }
    ],
    "tolerance": 0.5
  }'
```

### 3. Create nesting job

```powershell
curl -X POST http://localhost:8000/v1/nesting/jobs `
  -H "Content-Type: application/json" `
  -d '{
    "mode": "batch_quantity",
    "parts": [
      {
        "part_id": "part-a",
        "filename": "part-a.dxf",
        "quantity": 2,
        "enabled": true,
        "fill_only": false,
        "polygon": {
          "points": [
            {"x": 0, "y": 0},
            {"x": 40, "y": 0},
            {"x": 40, "y": 20},
            {"x": 0, "y": 20},
            {"x": 0, "y": 0}
          ]
        }
      }
    ],
    "sheet": {
      "sheet_id": "sheet-1",
      "width": 100,
      "height": 100,
      "quantity": 1,
      "units": "mm"
    },
    "params": {
      "gap": 2.0,
      "rotation": [0, 180],
      "objective": "maximize_yield"
    }
  }'
```

### 4. Check job status

```powershell
curl http://localhost:8000/v1/nesting/jobs/<job-id>
```

### 5. Read result

```powershell
curl http://localhost:8000/v1/nesting/jobs/<job-id>/result
```

## Local configuration

All configuration is read from `app/settings.py` through `NESTING_*` environment variables.

Main variables:

- `NESTING_DATABASE_URL`
- `NESTING_REDIS_URL`
- `NESTING_STORAGE_DIR`
- `NESTING_GEOMETRY_TOLERANCE`
- `NESTING_STARTUP_TIMEOUT_SECONDS`
- `NESTING_QUEUE_BLOCK_TIMEOUT_SECONDS`

## Troubleshooting

- API container exits on startup: check `docker compose logs api`; the app waits for PostgreSQL and Redis before booting.
- Worker does not process jobs: check `docker compose logs worker` and confirm Redis is healthy.
- `docker compose up --build` does not work on Windows: make sure Docker Desktop is installed and running.
- `/health` does not respond: wait for the `api` healthcheck to turn healthy in `docker compose ps`, then retry.
- Result endpoint returns `409`: the job is still `CREATED` or `RUNNING`, or it failed.
- Result endpoint returns `404`: confirm the job id exists.
- Local tests fail on Windows Store Python: install real Python 3.11 instead of the WindowsApps launcher.

## URLs

- Backend URL: `http://localhost:8000`
- Frontend URL: `http://localhost:5173`
