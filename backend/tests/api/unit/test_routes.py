"""
Unit tests for API routes.

These tests verify route handlers using mocked dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime
import json
import time

# Mock the dependencies before importing routes
# This prevents the module-level producer and redis_client from being created


@pytest.fixture
def mock_producer():
    """Create a mock Kafka producer."""
    producer = MagicMock()
    producer.flush.return_value = 0
    return producer


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.ping.return_value = True
    return client


@pytest.fixture
def client(mock_producer, mock_redis_client, monkeypatch):
    """Create a test client with mocked dependencies."""
    # Mock create_producer and create_redis_connection before import
    monkeypatch.setattr(
        "shared.kafka.create_producer", lambda config=None: mock_producer
    )
    monkeypatch.setattr(
        "api.redis.create_redis_connection", lambda: mock_redis_client
    )
    
    # Mock rate limiter functions to always allow requests (return a client IP)
    # This must be done before importing routes
    monkeypatch.setattr(
        "api.ratelimiter.rate_limit_request", 
        lambda request, redis_client, limits=None: "127.0.0.1"
    )
    monkeypatch.setattr(
        "api.ratelimiter.rate_limit_press", 
        lambda request, redis_client: "127.0.0.1"
    )
    
    # Mock PoW verification to always pass
    monkeypatch.setattr(
        "api.pow.verify_solution",
        lambda redis_client, solution: (True, None)
    )

    # Now import routes (which will use our mocked functions)
    import importlib
    import api.routes as routes_module

    # Reload to pick up the mocked functions
    importlib.reload(routes_module)

    # Replace the already-created producer and redis_client
    monkeypatch.setattr(routes_module, "producer", mock_producer)
    monkeypatch.setattr(routes_module, "redis_client", mock_redis_client)

    return TestClient(routes_module.app)


class TestPressButton:
    """Unit tests for POST /v1/events/press endpoint."""
    
    @pytest.fixture(autouse=True)
    def press_request_body(self):
        """Valid press request body for all tests."""
        return {
            "challenge_id": "test-challenge-id",
            "difficulty": 4,
            "expires_at": int(time.time() * 1000) + 60000,
            "signature": "test-signature",
            "nonce": "test-nonce",
        }

    def test_returns_202_on_success(self, client, mock_producer, press_request_body):
        """Should return 202 Accepted with request_id and timestamp."""
        response = client.post("/v1/events/press", json=press_request_body)

        assert response.status_code == 202
        data = response.json()
        assert "request_id" in data
        assert "timestamp_ms" in data
        assert isinstance(data["request_id"], str)
        assert isinstance(data["timestamp_ms"], int)

    def test_request_id_is_hex_uuid(self, client, mock_producer, press_request_body):
        """Should return a valid hex UUID as request_id."""
        response = client.post("/v1/events/press", json=press_request_body)

        data = response.json()
        # UUID hex should be 32 characters
        assert len(data["request_id"]) == 32
        # Should be valid hex
        int(data["request_id"], 16)

    def test_timestamp_is_current(self, client, mock_producer, press_request_body):
        """Should return a timestamp close to current time."""
        import time

        before = int(time.time() * 1000)
        response = client.post("/v1/events/press", json=press_request_body)
        after = int(time.time() * 1000)

        data = response.json()
        assert before <= data["timestamp_ms"] <= after

    def test_sends_message_to_kafka(self, client, mock_producer, monkeypatch, press_request_body):
        """Should send message to Kafka with correct payload."""
        sent_messages = []

        def capture_send(producer, value, key=None, topic=None):
            sent_messages.append({"value": value, "key": key})

        import api.routes as routes_module

        monkeypatch.setattr(routes_module, "send_message", capture_send)

        response = client.post("/v1/events/press", json=press_request_body)

        assert len(sent_messages) == 1
        assert "timestamp_ms" in sent_messages[0]["value"]
        assert "request_id" in sent_messages[0]["value"]

    def test_returns_503_when_flush_times_out(self, client, mock_producer, monkeypatch, press_request_body):
        """Should return 503 when message flush times out."""
        import api.routes as routes_module

        # Simulate messages remaining after flush
        def mock_flush(producer):
            return 1  # 1 message still in queue

        monkeypatch.setattr(routes_module, "flush_producer", mock_flush)

        response = client.post("/v1/events/press", json=press_request_body)

        assert response.status_code == 503
        assert "timed out" in response.json()["detail"].lower()

    def test_returns_503_on_buffer_error(self, client, mock_producer, monkeypatch, press_request_body):
        """Should return 503 when producer buffer is full."""
        import api.routes as routes_module

        def mock_send(*args, **kwargs):
            raise BufferError("Buffer full")

        monkeypatch.setattr(routes_module, "send_message", mock_send)

        response = client.post("/v1/events/press", json=press_request_body)

        assert response.status_code == 503
        assert "overloaded" in response.json()["detail"].lower()

    def test_returns_503_on_kafka_exception(self, client, mock_producer, monkeypatch, press_request_body):
        """Should return 503 when Kafka raises an exception."""
        import api.routes as routes_module
        from shared.kafka import KafkaException

        def mock_send(*args, **kwargs):
            raise KafkaException("Broker unavailable")

        monkeypatch.setattr(routes_module, "send_message", mock_send)

        response = client.post("/v1/events/press", json=press_request_body)

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()


class TestGetCurrentState:
    """Unit tests for GET /v1/states/current endpoint."""

    def test_returns_state_when_found(self, client, monkeypatch):
        """Should return 200 with state data when state exists."""
        import api.routes as routes_module
        from datetime import datetime, timezone
        from api.schemas import Phase

        mock_state = {
            "id": 1,
            "last_applied_offset": 100,
            "counter": 42,
            "phase": Phase.CALM,
            "entropy": 0.5,
            "reveal_until_ms": 1000,
            "cooldown_ms": 500,
            "updated_at_ms": 1234567890,
            "created_at": datetime.now(timezone.utc),
        }

        monkeypatch.setattr(routes_module, "get_latest_state", lambda: mock_state)

        response = client.get("/v1/states/current")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["counter"] == 42

    def test_returns_404_when_no_state(self, client, monkeypatch):
        """Should return 404 when no state is found."""
        import api.routes as routes_module

        def mock_get_state():
            raise LookupError("No state found")

        monkeypatch.setattr(routes_module, "get_latest_state", mock_get_state)

        response = client.get("/v1/states/current")

        assert response.status_code == 404
        assert "no state found" in response.json()["detail"].lower()


class TestStreamState:
    """Unit tests for GET /v1/states/stream endpoint."""

    def test_returns_event_stream_content_type(self, client, monkeypatch):
        """Should return text/event-stream content type."""
        import api.routes as routes_module

        async def mock_listen():
            # Empty generator
            if False:
                yield

        monkeypatch.setattr(routes_module, "listen_on_pubsub", mock_listen)

        response = client.get("/v1/states/stream")

        assert response.headers["content-type"].startswith("text/event-stream")

    def test_returns_correct_headers(self, client, monkeypatch):
        """Should return cache-control and connection headers."""
        import api.routes as routes_module

        async def mock_listen():
            if False:
                yield

        monkeypatch.setattr(routes_module, "listen_on_pubsub", mock_listen)

        response = client.get("/v1/states/stream")

        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"


class TestHealthCheck:
    """Unit tests for GET /health endpoint."""

    def test_returns_200_when_all_healthy(self, client, monkeypatch):
        """Should return 200 when all checks pass."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=True, latency_ms=1.0)

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.0)

        def mock_db_health(session):
            return HealthCheckResult(healthy=True, latency_ms=3.0)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)
        monkeypatch.setattr(routes_module, "check_database_health", mock_db_health)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "checks" in data

    def test_returns_503_when_any_unhealthy(self, client, monkeypatch):
        """Should return 503 when any check fails."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=False, message="Connection refused")

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.0)

        def mock_db_health(session):
            return HealthCheckResult(healthy=True, latency_ms=3.0)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)
        monkeypatch.setattr(routes_module, "check_database_health", mock_db_health)

        response = client.get("/health")

        assert response.status_code == 503

    def test_includes_all_check_results(self, client, monkeypatch):
        """Should include results for all checked components."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=True, latency_ms=1.5)

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.5, message="2 broker(s)")

        def mock_db_health(session):
            return HealthCheckResult(healthy=True, latency_ms=3.5)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)
        monkeypatch.setattr(routes_module, "check_database_health", mock_db_health)

        response = client.get("/health")

        data = response.json()
        assert "redis" in data["checks"]
        assert "kafka" in data["checks"]
        assert "database" in data["checks"]


class TestLivenessProbe:
    """Unit tests for GET /health/live endpoint."""

    def test_returns_200_always(self, client):
        """Should always return 200 - confirms service is running."""
        response = client.get("/health/live")

        assert response.status_code == 200

    def test_returns_alive_status(self, client):
        """Should return status: alive."""
        response = client.get("/health/live")

        data = response.json()
        assert data["status"] == "alive"

    def test_does_not_check_dependencies(self, client, mock_redis_client, mock_producer):
        """Should not check external dependencies."""
        # Break the dependencies
        mock_redis_client.ping.side_effect = Exception("Redis is down!")
        mock_producer.list_topics.side_effect = Exception("Kafka is down!")

        # Should still return 200
        response = client.get("/health/live")

        assert response.status_code == 200


class TestReadinessProbe:
    """Unit tests for GET /health/ready endpoint."""

    def test_returns_200_when_ready(self, client, monkeypatch):
        """Should return 200 when critical dependencies are healthy."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=True, latency_ms=1.0)

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.0)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)

        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_returns_503_when_redis_unhealthy(self, client, monkeypatch):
        """Should return 503 when Redis is unhealthy."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=False, message="Connection refused")

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.0)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)

        response = client.get("/health/ready")

        assert response.status_code == 503

    def test_returns_503_when_kafka_unhealthy(self, client, monkeypatch):
        """Should return 503 when Kafka is unhealthy."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=True, latency_ms=1.0)

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=False, message="No brokers")

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)

        response = client.get("/health/ready")

        assert response.status_code == 503

    def test_includes_check_details(self, client, monkeypatch):
        """Should include details for both Redis and Kafka checks."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=True, latency_ms=1.0)

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.0)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)

        response = client.get("/health/ready")

        data = response.json()
        assert "redis" in data["checks"]
        assert "kafka" in data["checks"]

    def test_does_not_check_database(self, client, monkeypatch):
        """Should not include database in readiness check."""
        import api.routes as routes_module
        from api.health import HealthCheckResult

        def mock_redis_health(client):
            return HealthCheckResult(healthy=True, latency_ms=1.0)

        def mock_kafka_health(producer):
            return HealthCheckResult(healthy=True, latency_ms=2.0)

        monkeypatch.setattr(routes_module, "check_redis_health", mock_redis_health)
        monkeypatch.setattr(routes_module, "check_kafka_health", mock_kafka_health)

        response = client.get("/health/ready")

        data = response.json()
        assert "database" not in data["checks"]

