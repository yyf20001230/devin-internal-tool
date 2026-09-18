# Base images come from Docker Hub by default; override for a mirror or internal registry, e.g.
#   docker build --build-arg BASE_REGISTRY=mirror.gcr.io/library .
# TOOLS=<comma-separated tool ids> builds an image that ships and serves only those tools, e.g.
#   docker build --build-arg TOOLS=kyc -t internal-tools-kyc .
# Leave TOOLS empty for the all-in-one image.
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
ARG TOOLS=
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DB_PATH=/data/data.db TOOLS_DIR=/app/tools KNOWLEDGE_DIR=/app/knowledge TOOLS=${TOOLS}
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ server/
COPY tools/ tools/
COPY knowledge/ knowledge/
COPY deploy/select_tools.py deploy/entrypoint.sh /
# Keep only the selected tool definitions in the image (shared _users.yaml and policies stay).
RUN python /select_tools.py
COPY --from=web /src/web/dist web/dist/
RUN chmod +x /entrypoint.sh && useradd -u 10001 -M -s /usr/sbin/nologin app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
