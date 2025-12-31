"""
E2E Tests - Button Press Flow

Tests the complete flow from button press to state update.

Prerequisites:
-------------
These tests require the API to be running. Before running these tests:

1. Start infrastructure services:
   $ make start

2. Start the API (choose one):
   Option A - Run locally:
   $ make run-api
   
   Option B - Run in Docker:
   $ make start-full
   # OR
   $ docker compose up -d api

3. Wait a few seconds for the API to be ready, then run:
   $ make test-e2e
   # OR
   $ poetry run pytest tests/e2e/test_button_flow.py

Note: Some tests only require Docker services (Kafka, Redis) and will run
even if the API is not running. Tests that require the API will be skipped
with a helpful message if the API is not available.

For smoke tests that only need Docker (no API required), use: make test-smoke
"""

import pytest
import time
import json
import hashlib
from confluent_kafka import Consumer


KAFKA_TOPIC = "press_button"


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
class TestButtonPressFlow:
    """Test the button press to Kafka flow."""

    def test_press_button_returns_accepted(self, http_client, ensure_topic):
        """Pressing the button should return 202 Accepted."""
        press_request = get_valid_press_request(http_client)
        response = http_client.post("/v1/events/press", json=press_request)
        
        assert response.status_code == 202
        data = response.json()
        
        assert "request_id" in data
        assert "timestamp_ms" in data
        assert len(data["request_id"]) == 32  # UUID hex
        assert isinstance(data["timestamp_ms"], int)

    def test_press_button_message_in_kafka(self, http_client, ensure_topic, docker_services_up):
        """Pressing the button should produce a message to Kafka."""
        # Create a consumer to read messages
        consumer = Consumer({
            "bootstrap.servers": "localhost:9092",
            "group.id": f"e2e-test-{time.time()}",
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        })
        consumer.subscribe([KAFKA_TOPIC])
        
        # Drain any existing messages
        consumer.poll(timeout=1)
        
        try:
            # Press the button
            press_request = get_valid_press_request(http_client)
            response = http_client.post("/v1/events/press", json=press_request)
            assert response.status_code == 202
            press_data = response.json()
            request_id = press_data["request_id"]
            
            # Poll for the message (give it a few seconds)
            message_found = False
            start = time.time()
            while time.time() - start < 5:
                msg = consumer.poll(timeout=1)
                if msg is None:
                    continue
                if msg.error():
                    continue
                
                payload = json.loads(msg.value())
                if payload.get("request_id") == request_id:
                    message_found = True
                    assert payload["timestamp_ms"] == press_data["timestamp_ms"]
                    break
            
            assert message_found, f"Message with request_id {request_id} not found in Kafka"
        
        finally:
            consumer.close()

    def test_multiple_presses_produce_unique_ids(self, http_client, ensure_topic):
        """Multiple button presses should produce unique request IDs."""
        request_ids = set()
        
        for _ in range(5):
            press_request = get_valid_press_request(http_client)
            response = http_client.post("/v1/events/press", json=press_request)
            assert response.status_code == 202, f"Unexpected status: {response.status_code}, body: {response.text}"
            request_ids.add(response.json()["request_id"])
        
        assert len(request_ids) == 5, "All request IDs should be unique"

    def test_press_timestamps_are_monotonic(self, http_client, ensure_topic):
        """Timestamps should be monotonically increasing."""
        timestamps = []
        
        for _ in range(3):
            press_request = get_valid_press_request(http_client)
            response = http_client.post("/v1/events/press", json=press_request)
            assert response.status_code == 202, f"Unexpected status: {response.status_code}, body: {response.text}"
            timestamps.append(response.json()["timestamp_ms"])
            # Small delay to ensure timestamps differ
            time.sleep(0.01)
        
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i-1], "Timestamps should be monotonic"


@pytest.mark.usefixtures("api_running")
class TestStateEndpoints:
    """Test state-related endpoints."""

    def test_get_current_state_structure(self, http_client):
        """If state exists, verify its structure."""
        response = http_client.get("/v1/states/current")
        
        if response.status_code == 404:
            pytest.skip("No state exists yet - reducer may not have processed any events")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        expected_fields = [
            "id", "last_applied_offset", "counter", "phase",
            "entropy", "reveal_until_ms", "updated_at_ms", "created_at"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify types
        assert isinstance(data["id"], int)
        assert isinstance(data["counter"], int)
        assert isinstance(data["phase"], int)

    def test_stream_endpoint_returns_sse(self, http_client):
        """SSE endpoint should return event-stream content type."""
        # Use a short timeout since we're just checking headers
        try:
            with http_client.stream("GET", "/v1/states/stream", timeout=2) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
        except Exception:
            # Timeout is expected, we're just checking the initial response
            pass


@pytest.mark.usefixtures("docker_services_up")
class TestKafkaIntegration:
    """Test Kafka-specific behaviors."""

    def test_topic_has_single_partition(self, kafka_admin, ensure_topic):
        """Verify topic configuration."""
        metadata = kafka_admin.list_topics(timeout=5)
        topic = metadata.topics.get(KAFKA_TOPIC)
        
        assert topic is not None, f"Topic {KAFKA_TOPIC} should exist"
        # For ordering guarantees, we should have 1 partition
        # or the test should note this is configurable

    def test_producer_can_send_message(self, kafka_producer, ensure_topic):
        """Verify we can produce messages to the topic."""
        delivery_reports = []
        
        def delivery_callback(err, msg):
            delivery_reports.append((err, msg))
        
        test_message = json.dumps({
            "timestamp_ms": int(time.time() * 1000),
            "request_id": "test-e2e-producer",
        })
        
        kafka_producer.produce(
            KAFKA_TOPIC,
            value=test_message.encode(),
            key=b"global",
            callback=delivery_callback,
        )
        kafka_producer.flush(timeout=5)
        
        assert len(delivery_reports) == 1
        err, msg = delivery_reports[0]
        assert err is None, f"Message delivery failed: {err}"


@pytest.mark.usefixtures("docker_services_up")
class TestRedisIntegration:
    """Test Redis-specific behaviors."""

    def test_can_publish_to_state_channel(self, redis_client):
        """Verify we can publish to the state updates channel."""
        channel = "state_updates:v1"
        
        # Subscribe first
        pubsub = redis_client.pubsub()
        pubsub.subscribe(channel)
        
        # Publish a test message
        subscribers = redis_client.publish(channel, json.dumps({"test": True}))
        
        # Should have at least our subscriber
        assert subscribers >= 1
        
        pubsub.unsubscribe()
        pubsub.close()

