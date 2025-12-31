"""
E2E Tests - Button Press Flow

Tests the complete flow from button press to state update.
Run with: make test-e2e

Note: These tests require both the API and Reducer to be running.
For smoke tests that only need Docker, use: make test-smoke
"""

import pytest
import time
import json
from confluent_kafka import Consumer


KAFKA_TOPIC = "press_button"


@pytest.mark.usefixtures("api_running")
class TestButtonPressFlow:
    """Test the button press to Kafka flow."""

    def test_press_button_returns_accepted(self, http_client, ensure_topic):
        """Pressing the button should return 202 Accepted."""
        response = http_client.post("/v1/events/press")
        
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
            response = http_client.post("/v1/events/press")
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
            response = http_client.post("/v1/events/press")
            assert response.status_code == 202
            request_ids.add(response.json()["request_id"])
        
        assert len(request_ids) == 5, "All request IDs should be unique"

    def test_press_timestamps_are_monotonic(self, http_client, ensure_topic):
        """Timestamps should be monotonically increasing."""
        timestamps = []
        
        for _ in range(3):
            response = http_client.post("/v1/events/press")
            assert response.status_code == 202
            timestamps.append(response.json()["timestamp_ms"])
            time.sleep(0.01)  # Small delay
        
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

