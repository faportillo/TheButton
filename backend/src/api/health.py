"""
Health check utilities for monitoring service dependencies.

Provides health check functions for:
- Redis connectivity
- Kafka producer connectivity
- Database connectivity

These are used by:
- /health endpoint for load balancer probes
- /health/ready endpoint for Kubernetes readiness probes
- /health/live endpoint for Kubernetes liveness probes
"""

import time
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from confluent_kafka import Producer
import redis

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    healthy: bool
    latency_ms: Optional[float] = None
    message: Optional[str] = None


def check_redis_health(redis_client: redis.Redis, timeout: float = 5.0) -> HealthCheckResult:
    """
    Check Redis connectivity by sending a PING command.

    Args:
        redis_client: Redis client instance
        timeout: Timeout in seconds for the health check

    Returns:
        HealthCheckResult with status and latency
    """
    try:
        start = time.perf_counter()
        result = redis_client.ping()
        latency_ms = (time.perf_counter() - start) * 1000

        if result:
            return HealthCheckResult(
                healthy=True,
                latency_ms=round(latency_ms, 2),
            )
        else:
            return HealthCheckResult(
                healthy=False,
                message="PING returned False",
            )

    except redis.ConnectionError as e:
        logger.warning(f"Redis health check failed: {e}")
        return HealthCheckResult(
            healthy=False,
            message=f"Connection error: {str(e)}",
        )
    except redis.TimeoutError as e:
        logger.warning(f"Redis health check timed out: {e}")
        return HealthCheckResult(
            healthy=False,
            message=f"Timeout after {timeout}s",
        )
    except Exception as e:
        logger.error(f"Unexpected error in Redis health check: {e}")
        return HealthCheckResult(
            healthy=False,
            message=f"Unexpected error: {str(e)}",
        )


def check_kafka_health(producer: Producer, timeout: float = 5.0) -> HealthCheckResult:
    """
    Check Kafka connectivity by listing topics.

    This verifies that:
    - The producer can connect to the broker
    - Metadata can be retrieved

    Args:
        producer: Kafka Producer instance
        timeout: Timeout in seconds for the health check

    Returns:
        HealthCheckResult with status and latency
    """
    try:
        start = time.perf_counter()
        metadata = producer.list_topics(timeout=timeout)
        latency_ms = (time.perf_counter() - start) * 1000

        # Check that we got valid metadata
        if metadata and len(metadata.brokers) > 0:
            return HealthCheckResult(
                healthy=True,
                latency_ms=round(latency_ms, 2),
                message=f"{len(metadata.brokers)} broker(s) available",
            )
        else:
            return HealthCheckResult(
                healthy=False,
                message="No brokers available",
            )

    except Exception as e:
        logger.warning(f"Kafka health check failed: {e}")
        return HealthCheckResult(
            healthy=False,
            message=f"Error: {str(e)}",
        )


def check_database_health(session_factory, timeout: float = 5.0) -> HealthCheckResult:
    """
    Check database connectivity by executing a simple query.

    Args:
        session_factory: SQLAlchemy sessionmaker
        timeout: Timeout in seconds for the health check

    Returns:
        HealthCheckResult with status and latency
    """
    try:
        from sqlalchemy import text

        start = time.perf_counter()

        with session_factory() as session:
            result = session.execute(text("SELECT 1"))
            result.fetchone()

        latency_ms = (time.perf_counter() - start) * 1000

        return HealthCheckResult(
            healthy=True,
            latency_ms=round(latency_ms, 2),
        )

    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return HealthCheckResult(
            healthy=False,
            message=f"Error: {str(e)}",
        )


def aggregate_health(
    checks: dict[str, HealthCheckResult],
) -> Tuple[str, dict]:
    """
    Aggregate multiple health check results into overall status.

    Args:
        checks: Dictionary of component name to HealthCheckResult

    Returns:
        Tuple of (overall_status, checks_dict)
        - overall_status: "healthy", "degraded", or "unhealthy"
        - checks_dict: Dictionary suitable for JSON response
    """
    all_healthy = all(c.healthy for c in checks.values())
    any_healthy = any(c.healthy for c in checks.values())

    if all_healthy:
        status = "healthy"
    elif any_healthy:
        status = "degraded"
    else:
        status = "unhealthy"

    checks_dict = {
        name: {
            "status": "healthy" if result.healthy else "unhealthy",
            "latency_ms": result.latency_ms,
            "message": result.message,
        }
        for name, result in checks.items()
    }

    return status, checks_dict

