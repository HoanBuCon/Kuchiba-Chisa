# ─────────────────────────────────────────────────────────────────────────────
# Chisa AI — Dockerfile
# Multi-stage build: builder → production
# Non-root user in production for security
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install into a target dir for easy copy to final stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production ───────────────────────────────────────────────────────
FROM python:3.11-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Non-root user for security
RUN groupadd --gid 1001 chisa && \
    useradd --uid 1001 --gid chisa --shell /bin/bash --create-home chisa

WORKDIR /app
RUN chown chisa:chisa /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=chisa:chisa app/ ./app/
COPY --chown=chisa:chisa alembic.ini ./
COPY --chown=chisa:chisa alembic_migrations/ ./alembic_migrations/

# Switch to non-root user
USER chisa

# Health check for container orchestrator
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health', timeout=5)"

EXPOSE 8000

# Default: run API server (overridden in docker-compose for worker)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ── Stage 3: Isolated verification ───────────────────────────────────────────
# Used only by docker-compose.test.yml and CI. Production images do not contain
# test, lint, or type-check dependencies.
FROM production AS test

USER root

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY --chown=chisa:chisa pyproject.toml ./
COPY --chown=chisa:chisa tests/ ./tests/

USER chisa
