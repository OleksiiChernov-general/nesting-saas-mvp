# Nesting SaaS MVP

## О проекте
`nesting_saas_mvp` — MVP-сервис для раскладки (nesting) деталей с REST API, асинхронной обработкой задач и экспортом результатов в CSV.

Основные компоненты:
- Backend: FastAPI (`app/`)
- Worker: очередь задач на Redis (`python -m app.worker`)
- Frontend: React + Vite (`frontend/`)
- Инфраструктура: PostgreSQL + Redis (`docker-compose.yml`)

## Установка
### Требования
- Python 3.11+
- Node.js 20+ и npm
- Docker (для PostgreSQL и Redis)

### 1. Клонирование и backend-зависимости
```powershell
git clone <url-репозитория>
cd nesting_saas_mvp
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Frontend-зависимости
```powershell
cd frontend
npm install
cd ..
```

## Использование
### Быстрый запуск через Docker Compose
```powershell
docker compose up -d --build
```

### Локальный запуск (по компонентам)
1. Поднять PostgreSQL и Redis:
```powershell
docker compose up -d postgres redis
```

2. Запустить API:
```powershell
.\.venv\Scripts\Activate.ps1
$env:NESTING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/nesting_mvp"
$env:NESTING_REDIS_URL = "redis://localhost:6379/0"
uvicorn app.main:app --reload
```

3. В отдельном терминале запустить worker:
```powershell
.\.venv\Scripts\Activate.ps1
$env:NESTING_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/nesting_mvp"
$env:NESTING_REDIS_URL = "redis://localhost:6379/0"
python -m app.worker
```

4. Запустить frontend:
```powershell
cd frontend
npm run dev
```

### Проверка API
```powershell
curl http://localhost:8000/health
```
Ожидаемый ответ:
```json
{"status":"ok"}
```

### Пример использования: экспорт артефакта в CSV
```powershell
powershell -ExecutionPolicy Bypass -File .\examples\export_artifact_to_csv.ps1 `
  -ArtifactPath .\artifact_<job_id>.json `
  -OutputCsvPath .\placements_<job_id>.csv
```

## Структура проекта
```text
.
|-- app/                 # Backend API, бизнес-логика и worker
|-- frontend/            # Веб-интерфейс (React + Vite)
|-- examples/            # Примеры входных/выходных файлов и скриптов
|-- scripts/             # Вспомогательные скрипты
|-- tests/               # Тесты
|-- storage/             # Локальное хранилище артефактов
|-- docker-compose.yml   # Локальная инфраструктура и сервисы
|-- requirements.txt     # Python-зависимости
`-- README.md
```

## Вклад
- Общие правила: `CONTRIBUTING.md`
- Перед PR рекомендуется запускать:
```powershell
pytest
cd frontend
npm run test
```

## Лицензия
Лицензия пока не указана отдельным файлом `LICENSE`.

## Контакты
- Вопросы и предложения: через Issues в репозитории.
- Для рабочих обсуждений по изменениям используйте Pull Request с описанием шагов проверки.
