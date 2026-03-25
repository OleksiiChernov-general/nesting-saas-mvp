FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start-backend.sh ./start-backend.sh
COPY tests ./tests
COPY pytest.ini ./pytest.ini
COPY README.md ./README.md

RUN mkdir -p /app/storage/imports /app/storage/results
RUN chmod +x /app/start-backend.sh

CMD ["./start-backend.sh"]
