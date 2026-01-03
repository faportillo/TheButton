"""
Smoke Tests

Quick health checks to verify all services are up and responding.
Run with: make test-smoke
"""

import pytest
import hashlib
from sqlalchemy import text


class TestInfrastructureSmoke:
    """Smoke tests for infrastructure services (no API needed)."""

    def test_postgres_connection(self, db_engine):
        """Verify PostgreSQL is accessible and responding."""
        with db_engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as health"))
            row = result.fetchone()
            assert row[0] == 1

    def test_postgres_tables_exist(self, db_engine):
        """Verify database schema is migrated."""
        # Use database-agnostic query that works for both PostgreSQL and SQLite
        with db_engine.connect() as conn:
            # Check database dialect
            dialect_name = db_engine.dialect.name
            if dialect_name == "postgresql":
                result = conn.execute(text("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('global_states', 'rulesets', 'alembic_version')
                """))
            elif dialect_name == "sqlite":
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' 
                    AND name IN ('global_states', 'rulesets', 'alembic_version')
                """))
            else:
                pytest.skip(f"Unsupported database dialect: {dialect_name}")
            
            tables = {row[0] for row in result}
        
        missing_tables = []
        if "global_states" not in tables:
            missing_tables.append("global_states")
        if "rulesets" not in tables:
            missing_tables.append("rulesets")
        if "alembic_version" not in tables:
            missing_tables.append("alembic_version")
        
        if missing_tables:
            pytest.fail(
                f"Missing tables: {', '.join(missing_tables)}. "
                f"Database migrations may not have been applied. "
                f"Run 'make start' or 'make db-upgrade' to apply migrations."
            )

    def test_redis_connection(self, redis_client):
        """Verify Redis is accessible and responding."""
        assert redis_client.ping() is True

    def test_redis_pubsub_works(self, redis_client):
        """Verify Redis pub/sub functionality."""
        pubsub = redis_client.pubsub()
        pubsub.subscribe("test_channel")
        
        # Publish a test message
        redis_client.publish("test_channel", "smoke_test")
        
        # Should receive subscribe confirmation and message
        messages = []
        for _ in range(2):
            msg = pubsub.get_message(timeout=1)
            if msg:
                messages.append(msg)
        
        pubsub.unsubscribe()
        pubsub.close()
        
        # At minimum we should get the subscribe confirmation
        assert len(messages) >= 1

    def test_kafka_connection(self, kafka_admin):
        """Verify Kafka is accessible."""
        metadata = kafka_admin.list_topics(timeout=10)
        assert metadata is not None

    def test_kafka_topic_exists_or_can_create(self, kafka_admin, ensure_topic):
        """Verify the press_button topic exists or can be created."""
        topics = kafka_admin.list_topics(timeout=5).topics
        assert "press_button" in topics


def solve_challenge(challenge_id: str, difficulty: int) -> str:
    """
    Solve a PoW challenge by finding a nonce.
    
    This is what the client needs to do:
    - Try nonces until SHA256(challenge_id + ":" + nonce) has required leading zeros
    """
    nonce = 0
    target = "0" * difficulty
    
    while True:
        nonce_str = str(nonce)
        message = f"{challenge_id}:{nonce_str}".encode()
        hash_result = hashlib.sha256(message).hexdigest()
        
        if hash_result.startswith(target):
            return nonce_str
        
        nonce += 1
        # Safety limit to prevent infinite loops
        if nonce > 1000000:
            raise ValueError("Could not solve challenge within reasonable time")


def get_valid_press_request(http_client) -> dict:
    """Get a challenge, solve it, and return a valid press request body."""
    # Get a challenge
    challenge_response = http_client.get("/v1/challenge")
    assert challenge_response.status_code == 200
    challenge = challenge_response.json()
    
    # Solve the challenge
    nonce = solve_challenge(
        challenge["challenge_id"],
        challenge["difficulty"]
    )
    
    # Return valid press request
    return {
        "challenge_id": challenge["challenge_id"],
        "difficulty": challenge["difficulty"],
        "expires_at": challenge["expires_at"],
        "signature": challenge["signature"],
        "nonce": nonce,
    }


@pytest.mark.usefixtures("api_running")
class TestAPISmoke:
    """Smoke tests for the API (requires API to be running)."""

    def test_liveness_probe(self, http_client):
        """Verify API liveness endpoint returns 200."""
        response = http_client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    def test_readiness_probe(self, http_client):
        """Verify API readiness endpoint works."""
        response = http_client.get("/health/ready")
        # May be 200 or 503 depending on connection state
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "checks" in data

    def test_health_endpoint(self, http_client):
        """Verify comprehensive health check returns expected structure."""
        response = http_client.get("/health")
        # May be 200 or 503 depending on connection state
        assert response.status_code in (200, 503)
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "checks" in data
        
        checks = data["checks"]
        assert "redis" in checks
        assert "kafka" in checks
        assert "database" in checks

    def test_press_endpoint_exists(self, http_client):
        """Verify press endpoint is available (may fail if dependencies down)."""
        # Get a valid press request with PoW solution
        press_request = get_valid_press_request(http_client)
        response = http_client.post("/v1/events/press", json=press_request)
        # 202 = success, 400 = invalid PoW (shouldn't happen with valid request),
        # 503 = kafka down, 422 = validation error (shouldn't happen with valid request)
        assert response.status_code in (202, 503), (
            f"Unexpected status code {response.status_code}. "
            f"Response: {response.text}"
        )

    def test_current_state_endpoint_exists(self, http_client):
        """Verify current state endpoint is available."""
        response = http_client.get("/v1/states/current")
        # 200 = has state, 404 = no state yet, both are valid
        assert response.status_code in (200, 404)

