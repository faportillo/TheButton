# =============================================================================
# TheButton - Multi-stage Dockerfile
# =============================================================================
# Build targets:
#   - api: FastAPI application server
#   - reducer: Kafka consumer/state reducer
#   - nginx: Nginx reverse proxy
#
# Usage:
#   docker build --target api -t thebutton-api .
#   docker build --target reducer -t thebutton-reducer .
#   docker build --target nginx -t thebutton-nginx .
# =============================================================================

# -----------------------------------------------------------------------------
# Base stage: Python with Poetry
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS base

# Prevent Python from writing bytecode and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry into its own venv
ENV POETRY_VERSION=1.8.4 \
    POETRY_HOME=/opt/poetry \
    POETRY_CACHE_DIR=/opt/.cache

RUN python -m venv $POETRY_HOME \
    && $POETRY_HOME/bin/pip install -U pip setuptools \
    && $POETRY_HOME/bin/pip install poetry==$POETRY_VERSION

# Add Poetry to PATH (but NOT as default python)
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

# -----------------------------------------------------------------------------
# Dependencies stage: Install Python dependencies
# -----------------------------------------------------------------------------
FROM base AS dependencies

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure Poetry to install into a local .venv in the project
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true

# Install dependencies (creates .venv in /app)
RUN poetry install --only main --no-interaction --no-ansi --no-root

# Add the virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# -----------------------------------------------------------------------------
# API stage: FastAPI application
# -----------------------------------------------------------------------------
FROM dependencies AS api

# Copy source code
COPY src/ ./src/

# Create non-root user for security
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash appuser \
    && chown -R appuser:appgroup /app

USER appuser

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Run FastAPI with uvicorn (uses .venv python via PATH)
CMD ["python", "-m", "uvicorn", "api.routes:app", "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------------
# Reducer stage: Kafka consumer
# -----------------------------------------------------------------------------
FROM dependencies AS reducer

# Copy source code
COPY src/ ./src/

# Create non-root user for security
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash appuser \
    && chown -R appuser:appgroup /app

USER appuser

# Run reducer main (uses .venv python via PATH)
CMD ["python", "-m", "reducer.main"]

# -----------------------------------------------------------------------------
# Nginx stage: Reverse proxy
# -----------------------------------------------------------------------------
FROM nginx:stable-alpine AS nginx

# Install wget for healthcheck
RUN apk add --no-cache wget

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Create log directory and set permissions
RUN mkdir -p /var/log/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    chown -R nginx:nginx /etc/nginx

# Expose port 80
EXPOSE 80

# Health check (using sh to check if nginx responds)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

# Run nginx
CMD ["nginx", "-g", "daemon off;"]
