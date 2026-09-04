# ─────────────────────────────────────────────────────────────────────────────
# Chisa AI — Developer Makefile
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help install dev test test-isolated lint format migrate worker clean

PYTHON = venv/Scripts/python
PIP = venv/Scripts/pip
PYTEST = venv/Scripts/pytest
RUFF = venv/Scripts/ruff
CELERY = venv/Scripts/celery
UVICORN = venv/Scripts/uvicorn

help:                          ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' Makefile | awk 'BEGIN {FS = ":.*##"}; {printf "  %-20s %s\n", $$1, $$2}'

install:                       ## Install all dependencies into venv
	$(PIP) install -r requirements-dev.txt

dev:                           ## Run development server with hot reload
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

test:                          ## Run test suite
	$(PYTEST) tests/ -v --cov=app --cov-report=term-missing

test-isolated:                 ## Run migration and checks against disposable Docker services
	@set -e; \
		cleanup() { docker compose -p kuchiba-chisa-test -f docker-compose.test.yml down --volumes --remove-orphans; }; \
		trap cleanup EXIT; \
		docker compose -p kuchiba-chisa-test -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test

lint:                          ## Run ruff linter
	$(RUFF) check app/ tests/

format:                        ## Auto-format with ruff
	$(RUFF) format app/ tests/
	$(RUFF) check --fix app/ tests/

migrate:                       ## Run Alembic migrations
	$(PYTHON) -m alembic upgrade head

migrate-new:                   ## Create new Alembic revision (usage: make migrate-new MSG="add users table")
	$(PYTHON) -m alembic revision --autogenerate -m "$(MSG)"

worker:                        ## Start Celery worker
	$(CELERY) -A app.infrastructure.queue.worker worker --loglevel=info -Q high,medium,low

worker-beat:                   ## Start Celery beat scheduler
	$(CELERY) -A app.infrastructure.queue.celery_app beat --loglevel=info

docker-up:                     ## Start all Docker services
	docker compose up -d

docker-down:                   ## Stop all Docker services
	docker compose down

docker-logs:                   ## Follow logs from all services
	docker compose logs -f

clean:                         ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage
