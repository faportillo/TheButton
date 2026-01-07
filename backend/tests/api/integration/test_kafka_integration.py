"""
Integration tests for Kafka producer using testcontainers.

These tests spin up a real Kafka instance to verify:
- Actual message production and consumption
- Serialization correctness
- Delivery confirmation

Requirements:
- Docker must be running
- First run will pull the Kafka image (~800MB)
"""

import json
import time

from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic
import pytest
import shared.constants as constants

# Try to import testcontainers, skip tests if not available or Docker not running
try:
    from testcontainers.kafka import KafkaContainer
    import docker
    # Quick check if Docker is available
    docker.from_env().ping()
    DOCKER_AVAILABLE = True
except Exception:
    DOCKER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker not available or not running"
)


@pytest.fixture(scope="module")
def kafka_container():
    """Spin up a real Kafka container for integration tests."""
    with KafkaContainer("confluentinc/cp-kafka:7.5.0") as container:
        yield container


@pytest.fixture
def kafka_bootstrap(kafka_container):
    """Get the bootstrap server address."""
    return kafka_container.get_bootstrap_server()


@pytest.fixture
def kafka_producer(kafka_bootstrap):
    """Create a Kafka producer connected to the test container."""
    config = {
        "bootstrap.servers": kafka_bootstrap,
        "client.id": "test-producer",
    }
    producer = Producer(config)
    yield producer
    producer.flush(timeout=5)


@pytest.fixture
def kafka_consumer(kafka_bootstrap):
    """Create a Kafka consumer connected to the test container."""
    config = {
        "bootstrap.servers": kafka_bootstrap,
        "group.id": "test-consumer-group",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
    consumer = Consumer(config)
    yield consumer
    consumer.close()


@pytest.fixture
def create_test_topic(kafka_bootstrap):
    """Factory to create test topics."""
    admin = AdminClient({"bootstrap.servers": kafka_bootstrap})
    created_topics = []

    def _create(topic_name: str, num_partitions: int = 1):
        topic = NewTopic(topic_name, num_partitions=num_partitions, replication_factor=1)
        futures = admin.create_topics([topic])
        for topic_name, future in futures.items():
            try:
                future.result(timeout=10)
                created_topics.append(topic_name)
            except Exception as e:
                # Topic might already exist
                pass
        return topic_name

    yield _create

    # Cleanup - delete created topics
    if created_topics:
        admin.delete_topics(created_topics)


class TestKafkaProducerIntegration:
    """Integration tests for Kafka producer functionality."""

    def test_produce_and_consume_message(
        self, kafka_producer, kafka_consumer, create_test_topic
    ):
        """Should successfully produce and consume a message."""
        topic = create_test_topic("test-produce-consume")

        # Produce a message
        message = {"id": 1, "data": "test"}
        kafka_producer.produce(
            topic=topic,
            key=b"test-key",
            value=json.dumps(message).encode("utf-8"),
        )
        kafka_producer.flush(timeout=10)

        # Consume the message
        kafka_consumer.subscribe([topic])

        msg = kafka_consumer.poll(timeout=10.0)

        assert msg is not None
        assert msg.error() is None
        assert msg.key() == b"test-key"
        assert json.loads(msg.value().decode("utf-8")) == message

    def test_produce_press_event_format(
        self, kafka_producer, kafka_consumer, create_test_topic
    ):
        """Should correctly produce press event in expected format."""
        topic = create_test_topic("test-press-events")

        # Produce a press event matching the API format
        press_event = {
            "timestamp_ms": int(time.time() * 1000),
            "request_id": "abc123def456",
        }
        kafka_producer.produce(
            topic=topic,
            key=constants.API_KAFKA_GLOBAL_KEY.encode("utf-8"),
            value=json.dumps(press_event).encode("utf-8"),
        )
        kafka_producer.flush(timeout=10)

        # Consume and verify
        kafka_consumer.subscribe([topic])
        msg = kafka_consumer.poll(timeout=10.0)

        assert msg is not None
        received = json.loads(msg.value().decode("utf-8"))
        assert "timestamp_ms" in received
        assert "request_id" in received
        assert received["request_id"] == "abc123def456"
        assert msg.key().decode("utf-8") == constants.API_KAFKA_GLOBAL_KEY

    def test_multiple_messages_ordering(
        self, kafka_producer, kafka_consumer, create_test_topic
    ):
        """Should maintain message ordering within a partition."""
        topic = create_test_topic("test-ordering")

        # Produce multiple messages with same key (same partition)
        for i in range(10):
            kafka_producer.produce(
                topic=topic,
                key=b"same-key",
                value=json.dumps({"sequence": i}).encode("utf-8"),
            )
        kafka_producer.flush(timeout=10)

        # Consume all messages
        kafka_consumer.subscribe([topic])
        received = []

        while len(received) < 10:
            msg = kafka_consumer.poll(timeout=5.0)
            if msg and not msg.error():
                received.append(json.loads(msg.value().decode("utf-8")))

        # Verify ordering
        sequences = [r["sequence"] for r in received]
        assert sequences == list(range(10))

    def test_delivery_callback_invoked(
        self, kafka_producer, create_test_topic
    ):
        """Should invoke delivery callback on successful send."""
        topic = create_test_topic("test-callback")
        delivery_results = []

        def on_delivery(err, msg):
            delivery_results.append({
                "error": err,
                "topic": msg.topic(),
                "partition": msg.partition(),
            })

        kafka_producer.produce(
            topic=topic,
            value=b"test-message",
            callback=on_delivery,
        )
        kafka_producer.flush(timeout=10)

        assert len(delivery_results) == 1
        assert delivery_results[0]["error"] is None
        assert delivery_results[0]["topic"] == topic

    def test_message_with_null_key(
        self, kafka_producer, kafka_consumer, create_test_topic
    ):
        """Should handle messages with null keys."""
        topic = create_test_topic("test-null-key")

        kafka_producer.produce(
            topic=topic,
            key=None,
            value=b"message-without-key",
        )
        kafka_producer.flush(timeout=10)

        kafka_consumer.subscribe([topic])
        msg = kafka_consumer.poll(timeout=10.0)

        assert msg is not None
        assert msg.key() is None
        assert msg.value() == b"message-without-key"


class TestKafkaConnectionIntegration:
    """Integration tests for Kafka connection handling."""

    def test_list_topics(self, kafka_bootstrap, create_test_topic):
        """Should list available topics."""
        topic = create_test_topic("test-list-topics")

        producer = Producer({"bootstrap.servers": kafka_bootstrap})
        metadata = producer.list_topics(timeout=10)

        assert topic in metadata.topics
        producer.flush()

    def test_producer_flush_returns_zero(self, kafka_producer, create_test_topic):
        """Should return zero remaining messages after flush."""
        topic = create_test_topic("test-flush")

        kafka_producer.produce(topic=topic, value=b"test")
        remaining = kafka_producer.flush(timeout=10)

        assert remaining == 0

    def test_broker_metadata(self, kafka_bootstrap):
        """Should retrieve broker metadata."""
        producer = Producer({"bootstrap.servers": kafka_bootstrap})
        metadata = producer.list_topics(timeout=10)

        assert len(metadata.brokers) >= 1
        producer.flush()

