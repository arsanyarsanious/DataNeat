FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1 CLOUDFLARE_EXPORT=1
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.lock.txt backend/pdf-dependencies.lock ./
RUN pip install --no-cache-dir -r requirements.lock.txt -r pdf-dependencies.lock
RUN useradd --create-home dataneat && mkdir /app/storage && chown dataneat:dataneat /app/storage
COPY --chown=dataneat:dataneat backend/app ./app
COPY --from=frontend /build/out /app/public
ENV STATIC_DIR=/app/public STORAGE_DIR=/app/storage PYTHONUNBUFFERED=1
USER dataneat
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
