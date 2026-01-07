# =============================================================================
# TheButton - Root Makefile
# =============================================================================
# Orchestrates both frontend and backend setup and execution
# Run `make help` to see all available targets
# =============================================================================

.PHONY: help setup setup-backend setup-frontend start start-backend start-frontend \
        start-full stop stop-frontend restart status logs clean install dev-install \
        run-api run-reducer run-frontend test

# Directories
BACKEND_DIR := backend
FRONTEND_DIR := frontend

# Frontend server port
FRONTEND_PORT := 3000

# Python HTTP server command (Python 3)
PYTHON_HTTP_SERVER := python3 -m http.server

# =============================================================================
# Quick Start
# =============================================================================

help: ## Show this help message
	@echo "TheButton - Root Makefile"
	@echo "=========================="
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Backend-specific commands:"
	@echo "  cd backend && make help"
	@echo ""

setup: setup-backend setup-frontend ## Set up both frontend and backend

setup-backend: ## Set up backend dependencies (Poetry install)
	@echo "Setting up backend dependencies..."
	@cd $(BACKEND_DIR) && poetry install
	@echo "✓ Backend dependencies installed"

setup-frontend: ## Verify frontend files exist (no build needed for static files)
	@echo "Checking frontend files..."
	@test -f $(FRONTEND_DIR)/index.html || (echo "Error: frontend/index.html not found" && exit 1)
	@test -f $(FRONTEND_DIR)/main.js || (echo "Error: frontend/main.js not found" && exit 1)
	@test -f $(FRONTEND_DIR)/styles.css || (echo "Error: frontend/styles.css not found" && exit 1)
	@echo "✓ Frontend files verified"

start: start-backend start-frontend ## Start both backend and frontend locally

start-backend: ## Start backend infrastructure and services locally
	@echo "Starting backend infrastructure..."
	@cd $(BACKEND_DIR) && $(MAKE) start
	@echo ""
	@echo "✓ Backend infrastructure running"
	@echo "  Run 'make run-api' and 'make run-reducer' in separate terminals,"
	@echo "  or use 'make start-full' to run everything in Docker"

start-frontend: ## Start frontend development server
	@if lsof -Pi :$(FRONTEND_PORT) -sTCP:LISTEN -t >/dev/null 2>&1 ; then \
		echo "Warning: Port $(FRONTEND_PORT) is already in use"; \
		echo "  Use 'make stop-frontend' to stop the existing server, or choose a different port"; \
		exit 1; \
	fi
	@echo "Starting frontend server on http://localhost:$(FRONTEND_PORT)..."
	@cd $(FRONTEND_DIR) && $(PYTHON_HTTP_SERVER) $(FRONTEND_PORT) > /tmp/thebutton-frontend.log 2>&1 & \
	echo $$! > /tmp/thebutton-frontend.pid
	@sleep 1
	@if [ -f /tmp/thebutton-frontend.pid ] && kill -0 $$(cat /tmp/thebutton-frontend.pid) 2>/dev/null; then \
		echo "✓ Frontend server started at http://localhost:$(FRONTEND_PORT)"; \
		echo "  PID: $$(cat /tmp/thebutton-frontend.pid)"; \
		echo "  Logs: /tmp/thebutton-frontend.log"; \
		echo "  Use 'make stop-frontend' to stop it"; \
	else \
		echo "✗ Failed to start frontend server. Check /tmp/thebutton-frontend.log for errors."; \
		rm -f /tmp/thebutton-frontend.pid; \
		exit 1; \
	fi

stop-frontend: ## Stop frontend development server
	@if [ -f /tmp/thebutton-frontend.pid ]; then \
		PID=$$(cat /tmp/thebutton-frontend.pid); \
		if kill $$PID 2>/dev/null; then \
			rm /tmp/thebutton-frontend.pid; \
			echo "✓ Frontend server stopped (PID: $$PID)"; \
		else \
			rm /tmp/thebutton-frontend.pid; \
			echo "Frontend server process not found. PID file removed."; \
		fi; \
	else \
		echo "Frontend server PID file not found. It may already be stopped."; \
		echo "You can also check for processes on port $(FRONTEND_PORT):"; \
		echo "  lsof -i :$(FRONTEND_PORT)"; \
	fi

start-full: ## Start everything in Docker (backend + frontend via nginx)
	@echo "Starting full stack in Docker..."
	@cd $(BACKEND_DIR) && $(MAKE) start-full
	@echo ""
	@echo "✓ Full stack running in Docker"
	@echo "  API: http://localhost:8000"
	@echo "  Nginx (with frontend): http://localhost:8080"
	@echo "  Health: http://localhost:8000/health"

stop: stop-frontend ## Stop all services (backend + frontend)
	@echo "Stopping backend services..."
	@cd $(BACKEND_DIR) && $(MAKE) stop
	@echo "✓ All services stopped"

restart: stop start-full ## Restart full stack

status: ## Show service status
	@echo "Backend services:"
	@cd $(BACKEND_DIR) && $(MAKE) status
	@echo ""
	@echo "Frontend: Check if process is running on port $(FRONTEND_PORT)"

logs: ## Follow logs (use SERVICE=api to filter)
	@cd $(BACKEND_DIR) && $(MAKE) logs SERVICE=$(SERVICE)

# =============================================================================
# Development
# =============================================================================

install: setup ## Install all dependencies (alias for setup)

dev-install: setup ## Install all dependencies including dev (alias for setup)

run-api: ## Run API locally (requires 'make start-backend' first)
	@echo "Starting API server..."
	@cd $(BACKEND_DIR) && $(MAKE) run-api

run-reducer: ## Run reducer locally (requires 'make start-backend' first)
	@echo "Starting reducer..."
	@cd $(BACKEND_DIR) && $(MAKE) run-reducer

run-frontend: start-frontend ## Run frontend server (alias for start-frontend)

# =============================================================================
# Testing
# =============================================================================

test: ## Run all backend tests
	@cd $(BACKEND_DIR) && $(MAKE) test

test-unit: ## Run unit tests only
	@cd $(BACKEND_DIR) && $(MAKE) test-unit

test-integration: ## Run integration tests (requires Docker)
	@cd $(BACKEND_DIR) && $(MAKE) test-integration

test-e2e: ## Run e2e tests (requires 'make start-full')
	@cd $(BACKEND_DIR) && $(MAKE) test-e2e

test-coverage: ## Run tests with coverage report
	@cd $(BACKEND_DIR) && $(MAKE) test-coverage

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Clean up cache and build artifacts
	@echo "Cleaning backend..."
	@cd $(BACKEND_DIR) && $(MAKE) clean
	@echo "✓ Cleanup complete"

