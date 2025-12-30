# =============================================================================
# TheButton - Makefile
# =============================================================================
# Run `make help` to see all available targets
# =============================================================================

.PHONY: help test test-unit test-integration test-contract test-api test-reducer \
        test-coverage test-verbose test-failed test-watch lint format clean \
        install dev-install docker-up docker-down

# Default Python and Poetry commands
PYTHON := poetry run python
PYTEST := poetry run pytest
BLACK := poetry run black

# Test directories
TEST_DIR := tests
API_UNIT_TESTS := tests/api/unit
API_INTEGRATION_TESTS := tests/api/integration
API_CONTRACT_TESTS := tests/api/contract
REDUCER_UNIT_TESTS := tests/reducer/unit
REDUCER_INTEGRATION_TESTS := tests/reducer/integration

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
# Docker
# =============================================================================

docker-up: ## Start all Docker services (postgres, redis, kafka)
	docker compose up -d postgres redis kafka

docker-up-all: ## Start all services including admin UIs
	docker compose --profile tools up -d

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
# Quick Reference
# =============================================================================

# Examples:
#   make test                    - Run all tests
#   make test-unit               - Run only unit tests
#   make test-integration        - Run only integration tests
#   make test-contract           - Run only contract tests
#   make test-match PATTERN="health"  - Run tests with "health" in name
#   make test-file FILE="tests/api/unit/test_kafka.py"  - Run specific file
#   make test-coverage           - Run with coverage report

