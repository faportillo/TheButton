"""
E2E Test Configuration

These tests run against real Docker services. Make sure to run:
    make start

Before running e2e tests:
    make test-e2e
"""

import os
import pytest
import time
from typing import Generator

# Set environment before any imports that might read config
# E2E tests require PostgreSQL - force it if not already set
os.environ.setdefault("API_ENV", "dev")
if "DATABASE_URL" not in os.environ or not os.environ["DATABASE_URL"].startswith("postgresql"):
    # E2E tests require PostgreSQL, not SQLite
    os.environ["DATABASE_URL"] = "postgresql://thebutton:thebutton@localhost:5433/thebutton"
os.environ.setdefault("KAFKA_BROKER_URL", "localhost:9092")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
# Bypass rate limiting for e2e tests to avoid flaky tests
os.environ.setdefault("RATE_LIMIT_BYPASS", "true")

import httpx
import redis
from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config


# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = "http://localhost:8000"

def get_database_url():
    """Get DATABASE_URL, ensuring it's PostgreSQL for e2e tests."""
    url = os.environ.get("DATABASE_URL", "postgresql://thebutton:thebutton@localhost:5433/thebutton")
    # E2E tests require PostgreSQL - force it if SQLite was set by other tests
    if not url.startswith("postgresql"):
        url = "postgresql://thebutton:thebutton@localhost:5433/thebutton"
        os.environ["DATABASE_URL"] = url
    return url

DATABASE_URL = get_database_url()
KAFKA_BROKER = os.environ["KAFKA_BROKER_URL"]
REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = int(os.environ["REDIS_PORT"])

KAFKA_TOPIC = "press_button"


# =============================================================================
# Service Health Checks
# =============================================================================

def wait_for_postgres(timeout: int = 30) -> bool:
    """Wait for PostgreSQL to be ready."""
    engine = create_engine(get_database_url())
    start = time.time()
    while time.time() - start < timeout:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            time.sleep(0.5)
    return False


def wait_for_redis(timeout: int = 30) -> bool:
    """Wait for Redis to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            client.ping()
            client.close()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def wait_for_kafka(timeout: int = 30) -> bool:
    """Wait for Kafka to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            admin = AdminClient({"bootstrap.servers": KAFKA_BROKER})
            metadata = admin.list_topics(timeout=5)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def wait_for_api(timeout: int = 30) -> bool:
    """Wait for API to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(f"{API_BASE_URL}/health/live", timeout=5)
            if response.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def docker_services_up():
    """Verify all Docker services are running before tests."""
    services = {
        "PostgreSQL": wait_for_postgres,
        "Redis": wait_for_redis,
        "Kafka": wait_for_kafka,
    }
    
    for name, check_fn in services.items():
        if not check_fn(timeout=10):
            pytest.skip(f"{name} is not available. Run 'make start' first.")
    
    yield


@pytest.fixture(scope="session")
def api_running(docker_services_up):
    """Verify API is running. Skip if not available.
    
    To run these tests, start the API first:
    - Option 1: Run API locally: make start && make run-api
    - Option 2: Run everything in Docker: make start-full
    - Option 3: Use Docker Compose: docker compose up -d api
    
    The API should be accessible at http://localhost:8000
    """
    if not wait_for_api(timeout=5):
        pytest.skip(
            "API is not running at http://localhost:8000.\n"
            "To run these e2e tests, start the API first:\n"
            "  • Run locally: make start && make run-api\n"
            "  • Run in Docker: make start-full\n"
            "  • Or use: docker compose up -d api\n"
            "Then wait a few seconds for the API to be ready and run the tests again."
        )
    yield


def ensure_migrations_applied():
    """Ensure database migrations are applied before tests run."""
    # Get the current DATABASE_URL (may have been changed by other tests)
    db_url = get_database_url()
    
    # Only run migrations for PostgreSQL - e2e tests require PostgreSQL
    if not db_url.startswith("postgresql"):
        # If not PostgreSQL, skip migrations (e.g., SQLite from other tests)
        # E2E tests should use PostgreSQL, so this is a configuration issue
        import logging
        logging.warning(
            f"Skipping migrations for non-PostgreSQL database: {db_url}. "
            f"E2E tests require PostgreSQL. Make sure DATABASE_URL is set correctly."
        )
        return
    
    try:
        alembic_cfg = Config("alembic.ini")
        # Set the database URL from environment
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        # Run migrations to head
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        # If migrations fail, raise an error with helpful message
        raise RuntimeError(
            f"Failed to apply database migrations: {e}. "
            f"Make sure the database is accessible and run 'make db-upgrade' manually."
        ) from e


@pytest.fixture(scope="session")
def db_engine(docker_services_up) -> Generator:
    """Create database engine for direct DB access in tests."""
    # Get the current DATABASE_URL (ensure it's PostgreSQL)
    db_url = get_database_url()
    
    # E2E tests require PostgreSQL - skip if using SQLite
    if not db_url.startswith("postgresql"):
        pytest.skip(
            f"E2E tests require PostgreSQL, but DATABASE_URL is {db_url}. "
            f"These tests are designed to run against the Docker PostgreSQL instance."
        )
    
    # Ensure migrations are applied before creating the engine
    ensure_migrations_applied()
    engine = create_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def redis_client(docker_services_up) -> Generator:
    """Create Redis client for tests."""
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    yield client
    client.close()


@pytest.fixture(scope="session")
def kafka_producer(docker_services_up) -> Generator:
    """Create Kafka producer for tests."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BROKER,
        "client.id": "e2e-test-producer",
    })
    yield producer
    producer.flush(timeout=5)


@pytest.fixture(scope="session")
def kafka_admin(docker_services_up) -> Generator:
    """Create Kafka admin client for tests."""
    admin = AdminClient({"bootstrap.servers": KAFKA_BROKER})
    yield admin


@pytest.fixture
def ensure_topic(kafka_admin):
    """Ensure the press_button topic exists."""
    try:
        topics = kafka_admin.list_topics(timeout=5).topics
        if KAFKA_TOPIC not in topics:
            new_topic = NewTopic(KAFKA_TOPIC, num_partitions=1, replication_factor=1)
            kafka_admin.create_topics([new_topic])
            time.sleep(1)  # Wait for topic creation
    except Exception as e:
        pytest.skip(f"Could not ensure Kafka topic: {e}")


@pytest.fixture
def http_client() -> Generator:
    """HTTP client for API requests."""
    with httpx.Client(base_url=API_BASE_URL, timeout=10) as client:
        yield client

