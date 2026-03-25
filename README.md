# Nesting SaaS MVP

Minimal backend for DXF import, geometry cleanup, asynchronous nesting jobs, and JSON results.

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
    "parts": [
      {
        "part_id": "part-a",
        "quantity": 2,
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
    "sheets": [
      {
        "sheet_id": "sheet-1",
        "width": 100,
        "height": 100,
        "quantity": 1
      }
    ],
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
