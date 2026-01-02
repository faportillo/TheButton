"""
Unit tests for health check functionality.

These tests verify the health check logic using mocked dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch
import redis
from api.health import (
    check_redis_health,
    check_kafka_health,
    check_database_health,
    aggregate_health,
    HealthCheckResult,
)


class FakeRedis:
    """Fake Redis client for testing."""

    def __init__(self, ping_result=True, raise_error=None):
        self._ping_result = ping_result
        self._raise_error = raise_error

    def ping(self):
        if self._raise_error:
            raise self._raise_error
        return self._ping_result


class FakeProducer:
    """Fake Kafka producer for testing."""

    def __init__(self, brokers=None, raise_error=None):
        self._brokers = brokers if brokers is not None else {1: "broker1"}
        self._raise_error = raise_error

    def list_topics(self, timeout=None):
        if self._raise_error:
            raise self._raise_error
        return FakeMetadata(self._brokers)


class FakeMetadata:
    """Fake Kafka metadata."""

    def __init__(self, brokers):
        self.brokers = brokers


class TestCheckRedisHealth:
    """Unit tests for check_redis_health function."""

    def test_returns_healthy_on_successful_ping(self):
        """Should return healthy when ping succeeds."""
        fake_redis = FakeRedis(ping_result=True)

        result = check_redis_health(fake_redis)

        assert result.healthy is True
        assert result.latency_ms is not None
        assert result.latency_ms >= 0
        assert result.message is None

    def test_returns_unhealthy_when_ping_returns_false(self):
        """Should return unhealthy when ping returns False."""
        fake_redis = FakeRedis(ping_result=False)

        result = check_redis_health(fake_redis)

        assert result.healthy is False
        assert result.message == "PING returned False"

    def test_returns_unhealthy_on_connection_error(self):
        """Should return unhealthy on ConnectionError."""
        fake_redis = FakeRedis(raise_error=redis.ConnectionError("Connection refused"))

        result = check_redis_health(fake_redis)

        assert result.healthy is False
        assert "Connection error" in result.message

    def test_returns_unhealthy_on_timeout_error(self):
        """Should return unhealthy on TimeoutError."""
        fake_redis = FakeRedis(raise_error=redis.TimeoutError("Timed out"))

        result = check_redis_health(fake_redis)

        assert result.healthy is False
        assert "Timeout" in result.message

    def test_returns_unhealthy_on_unexpected_error(self):
        """Should return unhealthy on unexpected errors."""
        fake_redis = FakeRedis(raise_error=RuntimeError("Unexpected"))

        result = check_redis_health(fake_redis)

        assert result.healthy is False
        assert "Unexpected error" in result.message

    def test_measures_latency(self):
        """Should measure and return latency."""
        fake_redis = FakeRedis(ping_result=True)

        result = check_redis_health(fake_redis)

        assert result.latency_ms is not None
        assert isinstance(result.latency_ms, float)


class TestCheckKafkaHealth:
    """Unit tests for check_kafka_health function."""

    def test_returns_healthy_with_brokers(self):
        """Should return healthy when brokers are available."""
        fake_producer = FakeProducer(brokers={1: "broker1", 2: "broker2"})

        result = check_kafka_health(fake_producer)

        assert result.healthy is True
        assert result.latency_ms is not None
        assert "2 broker(s)" in result.message

    def test_returns_unhealthy_with_no_brokers(self):
        """Should return unhealthy when no brokers are available."""
        fake_producer = FakeProducer(brokers={})

        result = check_kafka_health(fake_producer)

        assert result.healthy is False
        assert "No brokers" in result.message

    def test_returns_unhealthy_on_error(self):
        """Should return unhealthy on Kafka errors."""
        fake_producer = FakeProducer(raise_error=Exception("Kafka error"))

        result = check_kafka_health(fake_producer)

        assert result.healthy is False
        assert "Error" in result.message

    def test_measures_latency(self):
        """Should measure and return latency."""
        fake_producer = FakeProducer(brokers={1: "broker1"})

        result = check_kafka_health(fake_producer)

        assert result.latency_ms is not None
        assert isinstance(result.latency_ms, float)


class TestCheckDatabaseHealth:
    """Unit tests for check_database_health function."""

    def test_returns_healthy_on_successful_query(self):
        """Should return healthy when query succeeds."""
        # Create a mock session factory
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = (1,)

        mock_factory = MagicMock()
        mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_factory.return_value.__exit__ = MagicMock(return_value=False)

        result = check_database_health(mock_factory)

        assert result.healthy is True
        assert result.latency_ms is not None

    def test_returns_unhealthy_on_error(self):
        """Should return unhealthy on database errors."""
        mock_factory = MagicMock()
        mock_factory.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )

        result = check_database_health(mock_factory)

        assert result.healthy is False
        assert "Error" in result.message


class TestAggregateHealth:
    """Unit tests for aggregate_health function."""

    def test_returns_healthy_when_all_checks_pass(self):
        """Should return 'healthy' when all checks pass."""
        checks = {
            "redis": HealthCheckResult(healthy=True, latency_ms=1.0),
            "kafka": HealthCheckResult(healthy=True, latency_ms=2.0),
            "database": HealthCheckResult(healthy=True, latency_ms=3.0),
        }

        status, checks_dict = aggregate_health(checks)

        assert status == "healthy"
        assert all(c["status"] == "healthy" for c in checks_dict.values())

    def test_returns_unhealthy_when_all_checks_fail(self):
        """Should return 'unhealthy' when all checks fail."""
        checks = {
            "redis": HealthCheckResult(healthy=False, message="Error"),
            "kafka": HealthCheckResult(healthy=False, message="Error"),
        }

        status, checks_dict = aggregate_health(checks)

        assert status == "unhealthy"
        assert all(c["status"] == "unhealthy" for c in checks_dict.values())

    def test_returns_degraded_when_some_checks_fail(self):
        """Should return 'degraded' when some checks fail."""
        checks = {
            "redis": HealthCheckResult(healthy=True, latency_ms=1.0),
            "kafka": HealthCheckResult(healthy=False, message="Error"),
        }

        status, checks_dict = aggregate_health(checks)

        assert status == "degraded"
        assert checks_dict["redis"]["status"] == "healthy"
        assert checks_dict["kafka"]["status"] == "unhealthy"

    def test_includes_latency_in_output(self):
        """Should include latency in output dict."""
        checks = {
            "redis": HealthCheckResult(healthy=True, latency_ms=1.5),
        }

        status, checks_dict = aggregate_health(checks)

        assert checks_dict["redis"]["latency_ms"] == 1.5

    def test_includes_message_in_output(self):
        """Should include message in output dict."""
        checks = {
            "redis": HealthCheckResult(healthy=False, message="Connection refused"),
        }

        status, checks_dict = aggregate_health(checks)

        assert checks_dict["redis"]["message"] == "Connection refused"

    def test_handles_empty_checks(self):
        """Should handle empty checks dict."""
        checks = {}

        status, checks_dict = aggregate_health(checks)

        # All of nothing is healthy
        assert status == "healthy"
        assert checks_dict == {}

