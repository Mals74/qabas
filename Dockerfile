# Qabas: one image with the React app (built here) and the FastAPI backend, plus ffmpeg for uploaded recordings.
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
ENV HAYSTACK_TELEMETRY_ENABLED=False \
    SHOW_SAMPLE=0 \
    PYTHONUNBUFFERED=1
WORKDIR /app/backend
# Render (and most hosts) give the port in $PORT
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
