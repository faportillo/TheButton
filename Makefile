# =============================================================================
# TheButton - Makefile
# =============================================================================
# Run `make help` to see all available targets
# =============================================================================

.PHONY: help start start-full stop restart restart-full status logs logs-apps \
        test test-unit test-integration test-contract test-api test-reducer \
        test-e2e test-smoke test-coverage test-verbose test-failed lint format clean \
        install dev-install run-api run-reducer \
        docker-up docker-up-infra docker-up-apps docker-up-api docker-up-reducer \
        docker-up-full docker-up-all docker-down docker-build docker-build-api docker-build-reducer \
        docker-logs docker-logs-api docker-logs-reducer docker-logs-apps \
        docker-restart-api docker-restart-reducer docker-restart-apps docker-rebuild \
        restart-api restart-reducer restart-kafka restart-redis restart-postgres restart-db \
        restart-apps restart-infra restart-all rebuild-api rebuild-reducer rebuild-apps \
        db-migrate db-upgrade db-downgrade db-current db-history db-heads db-seed-rules

# Default Python and Poetry commands
PYTHON := poetry run python
PYTEST := poetry run pytest
BLACK := poetry run black
ALEMBIC := poetry run alembic

# Test directories
TEST_DIR := tests
API_UNIT_TESTS := tests/api/unit
API_INTEGRATION_TESTS := tests/api/integration
API_CONTRACT_TESTS := tests/api/contract
REDUCER_UNIT_TESTS := tests/reducer/unit
REDUCER_INTEGRATION_TESTS := tests/reducer/integration
E2E_TESTS := tests/e2e

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

start-full: ## Start everything in Docker (infra + api + reducer)
	@echo "Starting TheButton (full stack)..."
	@docker compose up -d --build
	@echo "Waiting for infrastructure to be healthy..."
	@sleep 5
	@docker compose exec -T api python -m alembic upgrade head 2>/dev/null || $(ALEMBIC) upgrade head
	@echo "✓ All services running in Docker."
	@echo "  API: http://localhost:8000"
	@echo "  Health: http://localhost:8000/health"

stop: ## Stop all services
	@echo "Stopping TheButton..."
	@docker compose --profile tools down
	@echo "✓ All services stopped."

restart: stop start ## Restart infrastructure services

restart-full: stop start-full ## Restart full stack (rebuild containers)

status: ## Show service status
	@docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

logs: ## Follow logs for all services
	@docker compose logs -f

logs-apps: ## Follow logs for API and reducer only
	@docker compose logs -f api reducer

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo "TheButton - Available Commands"
	@echo "=============================="
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Test Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# All Tests
# =============================================================================

test: ## Run all tests
	$(PYTEST) -v

test-all: test ## Alias for 'test'

test-fast: ## Run all tests without integration tests (faster)
	$(PYTEST) -v --ignore=$(API_INTEGRATION_TESTS) --ignore=$(REDUCER_INTEGRATION_TESTS)

# =============================================================================
# Unit Tests
# =============================================================================

test-unit: ## Run all unit tests
	$(PYTEST) $(API_UNIT_TESTS) $(REDUCER_UNIT_TESTS) -v

test-unit-api: ## Run API unit tests only
	$(PYTEST) $(API_UNIT_TESTS) -v

test-unit-reducer: ## Run reducer unit tests only
	$(PYTEST) $(REDUCER_UNIT_TESTS) -v

# =============================================================================
# Integration Tests
# =============================================================================

test-integration: ## Run all integration tests (requires Docker)
	$(PYTEST) $(API_INTEGRATION_TESTS) $(REDUCER_INTEGRATION_TESTS) -v

test-integration-api: ## Run API integration tests only
	$(PYTEST) $(API_INTEGRATION_TESTS) -v

test-integration-reducer: ## Run reducer integration tests only
	$(PYTEST) $(REDUCER_INTEGRATION_TESTS) -v

test-integration-redis: ## Run Redis integration tests only
	$(PYTEST) $(API_INTEGRATION_TESTS)/test_redis_integration.py -v

test-integration-kafka: ## Run Kafka integration tests only (requires Docker)
	$(PYTEST) $(API_INTEGRATION_TESTS)/test_kafka_integration.py -v

# =============================================================================
# Contract Tests
# =============================================================================

test-contract: ## Run contract tests
	$(PYTEST) $(API_CONTRACT_TESTS) -v

# =============================================================================
# E2E & Smoke Tests (requires Docker services)
# =============================================================================

test-smoke: ## Run smoke tests (quick health checks, requires 'make start')
	$(PYTEST) $(E2E_TESTS)/test_smoke.py -v

test-e2e: ## Run full e2e tests (requires 'make start' + API running)
	$(PYTEST) $(E2E_TESTS) -v

test-e2e-infra: ## Run e2e infrastructure tests only (no API needed)
	$(PYTEST) $(E2E_TESTS)/test_smoke.py::TestInfrastructureSmoke -v

# =============================================================================
# By Module
# =============================================================================

test-api: ## Run all API tests (unit + integration + contract)
	$(PYTEST) tests/api -v

test-reducer: ## Run all reducer tests
	$(PYTEST) tests/reducer -v

# =============================================================================
# Specific Test Patterns
# =============================================================================

# Usage: make test-match PATTERN="test_health"
test-match: ## Run tests matching a pattern (use PATTERN=...)
	$(PYTEST) -v -k "$(PATTERN)"

# Usage: make test-file FILE="tests/api/unit/test_health.py"
test-file: ## Run a specific test file (use FILE=...)
	$(PYTEST) $(FILE) -v

# Usage: make test-func FUNC="test_returns_healthy"
test-func: ## Run tests matching a function name (use FUNC=...)
	$(PYTEST) -v -k "$(FUNC)"

# =============================================================================
# Test Options
# =============================================================================

test-verbose: ## Run all tests with extra verbose output
	$(PYTEST) -vv --tb=long

test-debug: ## Run tests with debug output (print statements visible)
	$(PYTEST) -v -s

test-failed: ## Run only previously failed tests
	$(PYTEST) --lf -v

test-failed-first: ## Run failed tests first, then the rest
	$(PYTEST) --ff -v

test-coverage: ## Run tests with coverage report
	$(PYTEST) --cov=src --cov-report=term-missing --cov-report=html -v
	@echo "\nCoverage HTML report: htmlcov/index.html"

test-coverage-unit: ## Run unit tests with coverage
	$(PYTEST) $(API_UNIT_TESTS) $(REDUCER_UNIT_TESTS) --cov=src --cov-report=term-missing -v

# =============================================================================
# Development
# =============================================================================

install: ## Install production dependencies
	poetry install --only main

dev-install: ## Install all dependencies (including dev)
	poetry install

setup-env: ## Copy example.env to .env (if .env doesn't exist)
	@if [ ! -f .env ]; then \
		cp example.env .env; \
		echo "Created .env from example.env"; \
	else \
		echo ".env already exists, skipping"; \
	fi

run-api: ## Run API locally (requires 'make start' first)
	$(PYTHON) -m uvicorn api.routes:app --reload --host 0.0.0.0 --port 8000

run-reducer: ## Run reducer locally (requires 'make start' first)
	$(PYTHON) -m reducer.main

lint: ## Run linter checks
	$(BLACK) --check src tests

format: ## Format code with black
	$(BLACK) src tests

clean: ## Clean up cache and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# =============================================================================
# Docker - Infrastructure
# =============================================================================

docker-up: ## Start infrastructure services (postgres, redis, kafka)
	docker compose up -d postgres redis kafka

docker-up-infra: docker-up ## Alias for docker-up

docker-down: ## Stop all Docker services
	docker compose --profile tools down

docker-logs: ## Follow logs for all services
	docker compose logs -f

docker-logs-kafka: ## Follow Kafka logs
	docker compose logs -f kafka

docker-logs-redis: ## Follow Redis logs
	docker compose logs -f redis

docker-logs-db: ## Follow PostgreSQL logs
	docker compose logs -f postgres

docker-ps: ## Show running containers
	docker compose ps

docker-clean: ## Stop and remove all containers, volumes, and networks
	docker compose --profile tools down -v --remove-orphans

docker-restart: ## Restart all services
	docker compose restart

docker-health: ## Check health of all services
	@echo "Checking service health..."
	@docker compose ps --format "table {{.Name}}\t{{.Status}}"

# =============================================================================
# Docker - Application Services
# =============================================================================

docker-build: ## Build API and reducer images
	docker compose build api reducer

docker-build-api: ## Build API image only
	docker compose build api

docker-build-reducer: ## Build reducer image only
	docker compose build reducer

docker-up-apps: ## Start API and reducer containers (requires infra running)
	docker compose up -d api reducer

docker-up-api: ## Start API container only
	docker compose up -d api

docker-up-reducer: ## Start reducer container only
	docker compose up -d reducer

docker-up-full: ## Start all services (infra + apps)
	docker compose up -d

docker-up-all: ## Start all services including admin UIs
	docker compose --profile tools up -d

docker-logs-api: ## Follow API logs
	docker compose logs -f api

docker-logs-reducer: ## Follow reducer logs
	docker compose logs -f reducer

docker-logs-apps: ## Follow API and reducer logs
	docker compose logs -f api reducer

docker-restart-api: ## Restart API container
	docker compose restart api

docker-restart-reducer: ## Restart reducer container
	docker compose restart reducer

docker-restart-apps: ## Restart API and reducer containers
	docker compose restart api reducer

docker-rebuild: ## Rebuild and restart API and reducer
	docker compose up -d --build api reducer

# =============================================================================
# Quick Restart Shortcuts
# =============================================================================
# Usage: make restart-<service> or make rebuild-<service>
# Examples:
#   make restart-api       - Restart API container
#   make restart-reducer   - Restart reducer container  
#   make restart-kafka     - Restart Kafka
#   make rebuild-api       - Rebuild and restart API

restart-api: ## Restart API container (shortcut)
	@echo "Restarting API..."
	@docker compose restart api
	@echo "✓ API restarted"

restart-reducer: ## Restart reducer container (shortcut)
	@echo "Restarting reducer..."
	@docker compose restart reducer
	@echo "✓ Reducer restarted"

restart-kafka: ## Restart Kafka container
	@echo "Restarting Kafka..."
	@docker compose restart kafka
	@echo "✓ Kafka restarted"

restart-redis: ## Restart Redis container
	@echo "Restarting Redis..."
	@docker compose restart redis
	@echo "✓ Redis restarted"

restart-postgres: ## Restart PostgreSQL container
	@echo "Restarting PostgreSQL..."
	@docker compose restart postgres
	@echo "✓ PostgreSQL restarted"

restart-db: restart-postgres ## Alias for restart-postgres

restart-apps: ## Restart API and reducer containers
	@echo "Restarting API and reducer..."
	@docker compose restart api reducer
	@echo "✓ Apps restarted"

restart-infra: ## Restart infrastructure (postgres, redis, kafka)
	@echo "Restarting infrastructure..."
	@docker compose restart postgres redis kafka
	@echo "✓ Infrastructure restarted"

restart-all: ## Restart all containers
	@echo "Restarting all services..."
	@docker compose restart
	@echo "✓ All services restarted"

rebuild-api: ## Rebuild and restart API container
	@echo "Rebuilding API..."
	@docker compose up -d --build api
	@echo "✓ API rebuilt and restarted"

rebuild-reducer: ## Rebuild and restart reducer container
	@echo "Rebuilding reducer..."
	@docker compose up -d --build reducer
	@echo "✓ Reducer rebuilt and restarted"

rebuild-apps: ## Rebuild and restart API and reducer
	@echo "Rebuilding apps..."
	@docker compose up -d --build api reducer
	@echo "✓ Apps rebuilt and restarted"

# =============================================================================
# Database Migrations (Alembic)
# =============================================================================

db-migrate: ## Create a new migration (use MSG="description")
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

db-upgrade: ## Apply all pending migrations
	$(ALEMBIC) upgrade head

db-downgrade: ## Rollback the last migration
	$(ALEMBIC) downgrade -1

db-current: ## Show current migration revision
	$(ALEMBIC) current

db-history: ## Show migration history
	$(ALEMBIC) history --verbose

db-heads: ## Show current head revisions
	$(ALEMBIC) heads

db-stamp: ## Stamp the database with a revision without running migrations (use REV="revision")
	$(ALEMBIC) stamp $(REV)

db-reset: ## Reset database to clean state (WARNING: destroys data)
	$(ALEMBIC) downgrade base

db-seed-rules: ## Seed the database with initial rules from config/rules.json
	PYTHONPATH=src $(PYTHON) -m scripts.seed_rules

db-seed-rules-force: ## Force re-seed rules even if hash exists
	PYTHONPATH=src $(PYTHON) -m scripts.seed_rules --force

# =============================================================================
# Quick Reference
# =============================================================================

# Quick Start:
#   make start                   - Start infra (Docker) + run migrations
#   make start-full              - Start everything in Docker (infra + apps)
#   make stop                    - Stop all services
#   make restart                 - Restart infrastructure
#   make restart-full            - Restart full stack
#   make status                  - Show service status
#   make logs                    - Follow all logs
#
# Running Locally (after 'make start'):
#   make run-api                 - Run API locally with hot reload
#   make run-reducer             - Run reducer locally
#
# Docker App Services:
#   make docker-build            - Build API and reducer images
#   make docker-up-apps          - Start API and reducer in Docker
#   make docker-up-full          - Start infra + apps in Docker
#   make docker-logs-apps        - Follow API and reducer logs
#   make docker-rebuild          - Rebuild and restart apps
#
# Quick Restart (shortcuts):
#   make restart-api             - Restart API container
#   make restart-reducer         - Restart reducer container
#   make restart-kafka           - Restart Kafka container
#   make restart-redis           - Restart Redis container
#   make restart-postgres        - Restart PostgreSQL container
#   make restart-apps            - Restart API and reducer
#   make restart-infra           - Restart postgres, redis, kafka
#   make restart-all             - Restart all containers
#   make rebuild-api             - Rebuild and restart API
#   make rebuild-reducer         - Rebuild and restart reducer
#   make rebuild-apps            - Rebuild and restart API + reducer
#
# Testing:
#   make test                    - Run all tests
#   make test-unit               - Run only unit tests
#   make test-integration        - Run only integration tests
#   make test-match PATTERN="health"  - Run tests with "health" in name
#   make test-coverage           - Run with coverage report
#
# Database:
#   make db-migrate MSG="add users table"  - Create a new migration
#   make db-upgrade              - Apply all pending migrations
#   make db-downgrade            - Rollback last migration
#   make db-seed-rules           - Seed initial rules from config/rules.json

