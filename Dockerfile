# Base images come from Docker Hub by default; override for a mirror or internal registry, e.g.
#   docker build --build-arg BASE_REGISTRY=mirror.gcr.io/library .
ARG BASE_REGISTRY=docker.io/library

# Stage 1: build the React UI
FROM ${BASE_REGISTRY}/node:20-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: runtime (FastAPI + SQLite + built UI)
FROM ${BASE_REGISTRY}/python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DB_PATH=/data/data.db TOOLS_DIR=/app/tools KNOWLEDGE_DIR=/app/knowledge
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ server/
COPY tools/ tools/
COPY knowledge/ knowledge/
COPY --from=web /src/web/dist web/dist/
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && useradd -u 10001 -M -s /usr/sbin/nologin app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
