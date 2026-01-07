# =============================================================================
# TheButton - Makefile
# =============================================================================
# Run `make help` to see all available targets
# =============================================================================

.PHONY: help start start-full stop restart status logs test test-unit test-integration \
        test-e2e test-coverage install dev-install run-api run-reducer run-watcher format lint clean \
        db-upgrade db-migrate load-test

# Default Python and Poetry commands
POETRY_PYTHON := $(shell poetry env info --path)/bin/python
PYTHON := $(POETRY_PYTHON)
PYTEST := poetry run pytest
BLACK := poetry run black
ALEMBIC := poetry run alembic

# =============================================================================
# Quick Start
# =============================================================================

start: ## Start infrastructure (Docker) + run migrations
	@echo "Starting TheButton infrastructure..."
	@docker compose up -d postgres redis kafka
	@echo "Waiting for services to be healthy..."
	@sleep 3
	@$(ALEMBIC) upgrade head
	@echo "✓ Infrastructure running. Database migrated."
	@echo "Run 'make run-api' and 'make run-reducer' to start apps locally,"
	@echo "or 'make start-full' to run everything in Docker."

start-full: ## Start everything in Docker (infra + api + reducer + watcher + nginx)
	@echo "Starting TheButton (full stack)..."
	@docker compose up -d --build
	@echo "Waiting for infrastructure to be healthy..."
	@sleep 5
	@echo "Running database migrations..."
	@docker compose exec -T api sh -c "cd /app && python -m alembic upgrade head" 2>/dev/null || \
		(echo "Warning: Could not run migrations in container, trying locally..." && \
		 $(ALEMBIC) upgrade head || echo "Migrations may need to be run manually")
	@echo "✓ All services running in Docker."
	@echo "  API: http://localhost:8000"
	@echo "  Nginx: http://localhost:8080"
	@echo "  Health: http://localhost:8000/health"

stop: ## Stop all services
	@echo "Stopping TheButton..."
	@docker compose --profile tools down
	@echo "✓ All services stopped."

restart: stop start-full ## Restart full stack

status: ## Show service status
	@docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

logs: ## Follow logs (use SERVICE=api to filter)
	@if [ -n "$(SERVICE)" ]; then \
		docker compose logs -f $(SERVICE); \
	else \
		docker compose logs -f; \
	fi

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo "TheButton - Available Commands"
	@echo "=============================="
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	$(PYTEST) -v

test-unit: ## Run unit tests only
	$(PYTEST) tests/api/unit tests/reducer/unit -v

test-integration: ## Run integration tests (requires Docker)
	$(PYTEST) tests/api/integration tests/reducer/integration -v

test-e2e: ## Run e2e tests (requires 'make start-full')
	$(PYTEST) tests/e2e -v

test-coverage: ## Run tests with coverage report
	$(PYTEST) --cov=src --cov-report=term-missing --cov-report=html -v
	@echo "\nCoverage HTML report: htmlcov/index.html"

# =============================================================================
# Development
# =============================================================================

install: ## Install production dependencies
	poetry install --only main

dev-install: ## Install all dependencies (including dev)
	poetry install

run-api: ## Run API locally (requires 'make start' first)
	$(PYTHON) -m uvicorn api.routes:app --reload --host 0.0.0.0 --port 8000

run-reducer: ## Run reducer locally (requires 'make start' first)
	$(PYTHON) -m reducer.main

run-watcher: ## Run watcher locally (requires 'make start' first)
	PYTHONPATH=src $(PYTHON) -m watcher.main

format: ## Format code with black
	$(BLACK) src tests

lint: ## Run linter checks
	$(BLACK) --check src tests

clean: ## Clean up cache and build artifacts
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true

# =============================================================================
# Database Migrations
# =============================================================================

db-upgrade: ## Apply all pending migrations
	$(ALEMBIC) upgrade head

db-migrate: ## Create a new migration (use MSG="description")
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

db-downgrade: ## Rollback the last migration
	$(ALEMBIC) downgrade -1

db-seed-rules: ## Seed database with initial rules from config/rules.json
	PYTHONPATH=src $(PYTHON) -m scripts.seed_rules

# =============================================================================
# Load Testing
# =============================================================================

load-test: ## Run load test (use REQUESTS=100 CONCURRENT=10 RATE=10)
	PYTHONPATH=src poetry run python -m scripts.load_test \
		--requests $(or $(REQUESTS),100) \
		--concurrent $(or $(CONCURRENT),10) \
		$(if $(RATE),--rate $(RATE),) \
		$(if $(BYPASS_POW),--bypass-pow,)

load-test-heavy: ## Run heavy load test (1000 requests, 50 concurrent)
	PYTHONPATH=src poetry run python -m scripts.load_test \
		--requests 1000 \
		--concurrent 50
