FROM node:22-alpine AS frontend

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS sqlite-build

ARG SQLITE_ARCHIVE=sqlite-autoconf-3530100.tar.gz
ARG SQLITE_SHA3_256=414432ae5719f6cdc485f3927e12c7ad107e2b8c6b434e5df2eadb5312bfabb5
ARG SQLITE_SOURCE_ID=c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl --fail --location --output "$SQLITE_ARCHIVE" "https://sqlite.org/2026/$SQLITE_ARCHIVE" \
    && tar --extract --gzip --file "$SQLITE_ARCHIVE" \
    && test "$(openssl dgst -sha3-256 -r "${SQLITE_ARCHIVE%.tar.gz}/sqlite3.c" | awk '{print $1}')" = "$SQLITE_SHA3_256" \
    && cd "${SQLITE_ARCHIVE%.tar.gz}" \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && /usr/local/bin/sqlite3 :memory: "SELECT sqlite_source_id();" | grep --fixed-strings "$SQLITE_SOURCE_ID"

FROM python:3.13-slim AS runtime

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /uvx /bin/
COPY --from=sqlite-build /usr/local/lib/libsqlite3.so* /usr/local/lib/
RUN ldconfig \
    && python -c "import sqlite3; assert sqlite3.sqlite_version_info >= (3, 51, 3), sqlite3.sqlite_version"

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev
COPY alembic.ini ./
COPY shiftguard/ ./shiftguard/
COPY --from=frontend /app/frontend/dist/ ./shiftguard/static/
RUN uv sync --locked --no-dev

# Unprivileged runtime. Only the artifact store and the read-only dataset mount
# point are owned by the service user; datasets are mounted at runtime, never
# copied into the image (see deploy/README.md).
RUN groupadd --system --gid 10001 shiftguard     && useradd --system --uid 10001 --gid shiftguard --home-dir /app --no-create-home shiftguard     && mkdir -p /app/var/artifacts /app/var/datasets     && chown -R shiftguard:shiftguard /app/var
USER shiftguard

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4     CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4).status == 200 else 1)"]
# One Uvicorn worker: the API process is the single ordinary-provider owner for its database.
CMD ["uvicorn", "shiftguard.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
