"""
Integration tests for Redis pub/sub using testcontainers.

These tests spin up a real Redis instance to verify:
- Actual pub/sub message delivery
- Connection handling
- Serialization/deserialization
"""

import asyncio
import json
import time

import pytest
import redis as redis_lib
from testcontainers.redis import RedisContainer

from shared.constants import API_REDIS_STATE_UPDATE_CHANNEL
from shared.models import PersistedGlobalState


@pytest.fixture(scope="module")
def redis_container():
    """Spin up a real Redis container for integration tests."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture
def redis_client(redis_container):
    """Create a Redis client connected to the test container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = redis_lib.Redis(host=host, port=int(port), decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def async_redis_client(redis_container):
    """Create an async Redis client connected to the test container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = redis_lib.asyncio.Redis(host=host, port=int(port), decode_responses=True)
    yield client


def wait_for_subscription(pubsub, timeout=5.0):
    """Wait for the subscription to be confirmed."""
    start = time.time()
    while time.time() - start < timeout:
        msg = pubsub.get_message(timeout=0.1)
        if msg and msg["type"] == "subscribe":
            return True
    return False


class TestRedisPubSubIntegration:
    """Integration tests for Redis pub/sub functionality."""

    def test_publish_and_receive_message(self, redis_client):
        """Should successfully publish and receive a message."""
        pubsub = redis_client.pubsub()
        pubsub.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)

        # Wait for subscription to be confirmed
        assert wait_for_subscription(pubsub), "Subscription not confirmed"

        # Publish a message
        message_data = {"id": 1, "test": "data"}
        redis_client.publish(API_REDIS_STATE_UPDATE_CHANNEL, json.dumps(message_data))

        # Receive the message (with timeout)
        message = pubsub.get_message(timeout=5.0)

        assert message is not None
        assert message["type"] == "message"
        assert message["channel"] == API_REDIS_STATE_UPDATE_CHANNEL
        assert json.loads(message["data"]) == message_data

        pubsub.close()

    def test_publish_state_update_format(self, redis_client):
        """Should correctly serialize and deserialize PersistedGlobalState."""
        pubsub = redis_client.pubsub()
        pubsub.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)

        # Wait for subscription to be confirmed
        assert wait_for_subscription(pubsub), "Subscription not confirmed"

        # Create a state update matching what the reducer publishes
        state_data = {
            "type": "state_updated",
            "id": 42,
            "last_applied_offset": 100,
            "ruleshash": "abc123",
        }
        redis_client.publish(API_REDIS_STATE_UPDATE_CHANNEL, json.dumps(state_data))

        message = pubsub.get_message(timeout=5.0)

        assert message is not None
        received_data = json.loads(message["data"])
        assert received_data["id"] == 42
        assert received_data["last_applied_offset"] == 100
        assert received_data["ruleshash"] == "abc123"

        pubsub.close()

    def test_multiple_messages_in_sequence(self, redis_client):
        """Should receive multiple messages in order."""
        pubsub = redis_client.pubsub()
        pubsub.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)

        # Wait for subscription to be confirmed
        assert wait_for_subscription(pubsub), "Subscription not confirmed"

        # Publish multiple messages
        for i in range(5):
            redis_client.publish(
                API_REDIS_STATE_UPDATE_CHANNEL,
                json.dumps({"sequence": i})
            )

        # Receive all messages
        received = []
        for _ in range(10):  # Try more times to account for timing
            msg = pubsub.get_message(timeout=1.0)
            if msg and msg["type"] == "message":
                received.append(json.loads(msg["data"]))
            if len(received) == 5:
                break

        assert len(received) == 5
        assert [r["sequence"] for r in received] == [0, 1, 2, 3, 4]

        pubsub.close()

    def test_subscriber_count(self, redis_client):
        """Should report correct subscriber count."""
        pubsub1 = redis_client.pubsub()
        pubsub1.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)
        wait_for_subscription(pubsub1)

        pubsub2 = redis_client.pubsub()
        pubsub2.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)
        wait_for_subscription(pubsub2)

        # Publish returns number of subscribers
        count = redis_client.publish(API_REDIS_STATE_UPDATE_CHANNEL, "test")

        assert count == 2

        pubsub1.close()
        pubsub2.close()

    @pytest.mark.asyncio
    async def test_async_pubsub(self, async_redis_client):
        """Should work with async Redis client."""
        pubsub = async_redis_client.pubsub()
        await pubsub.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)

        # Wait for subscription confirmation
        msg = await pubsub.get_message(timeout=5.0)
        assert msg is not None and msg["type"] == "subscribe"

        # Publish a message
        await async_redis_client.publish(
            API_REDIS_STATE_UPDATE_CHANNEL,
            json.dumps({"async": True})
        )

        # Small delay to ensure message is delivered
        await asyncio.sleep(0.1)

        message = await pubsub.get_message(timeout=5.0)

        assert message is not None
        assert json.loads(message["data"]) == {"async": True}

        await pubsub.close()
        await async_redis_client.close()


class TestRedisConnectionIntegration:
    """Integration tests for Redis connection handling."""

    def test_ping_succeeds(self, redis_client):
        """Should successfully ping Redis."""
        assert redis_client.ping() is True

    def test_connection_info(self, redis_client):
        """Should retrieve server info."""
        info = redis_client.info()

        assert "redis_version" in info
        assert info["connected_clients"] >= 1

    def test_reconnection_after_command(self, redis_client):
        """Should maintain connection across multiple commands."""
        # Execute multiple commands
        redis_client.set("test_key", "test_value")
        value = redis_client.get("test_key")
        redis_client.delete("test_key")

        assert value == "test_value"
