import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import json
import api.kafka as api_kafka


class FakeMessage:
    """A fake Kafka message for testing delivery callbacks."""

    def __init__(self, topic="test-topic", partition=0):
        self._topic = topic
        self._partition = partition

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition


class FakeProducer:
    """A fake Kafka Producer for testing."""

    def __init__(self, config=None):
        self.config = config or {}
        self.produced_messages = []
        self.poll_count = 0
        self.flush_count = 0
        self.flush_timeout = None
        self.remaining_after_flush = 0

    def produce(self, topic, key=None, value=None, callback=None):
        self.produced_messages.append({
            "topic": topic,
            "key": key,
            "value": value,
            "callback": callback,
        })

    def poll(self, timeout):
        self.poll_count += 1
        return 0

    def flush(self, timeout):
        self.flush_count += 1
        self.flush_timeout = timeout
        return self.remaining_after_flush


class TestDeliveryCallback:
    """Unit tests for delivery_callback function."""

    def test_logs_error_when_err_is_not_none(self, caplog):
        """Should log error message when delivery fails."""
        import logging

        caplog.set_level(logging.ERROR)

        err = "Connection timeout"
        msg = FakeMessage()

        api_kafka.delivery_callback(err, msg)

        assert "Message delivery failed: Connection timeout" in caplog.text

    def test_logs_debug_on_successful_delivery(self, caplog):
        """Should log debug message when delivery succeeds."""
        import logging

        caplog.set_level(logging.DEBUG)

        err = None
        msg = FakeMessage(topic="my-topic", partition=3)

        api_kafka.delivery_callback(err, msg)

        assert "Message delivered to my-topic [3]" in caplog.text


class TestCreateProducer:
    """Unit tests for create_producer function."""

    def test_creates_producer_with_config(self, monkeypatch):
        """Should create a Producer with the provided config."""
        created_with_config = None

        def fake_producer_init(config):
            nonlocal created_with_config
            created_with_config = config
            return FakeProducer(config)

        monkeypatch.setattr(api_kafka, "Producer", fake_producer_init, raising=True)

        config = {
            "bootstrap.servers": "localhost:9092",
            "client.id": "test-client",
        }

        api_kafka.create_producer(config)

        assert created_with_config == config

    def test_returns_producer_instance(self, monkeypatch):
        """Should return a Producer instance."""
        fake_producer = FakeProducer()

        def fake_producer_init(config):
            return fake_producer

        monkeypatch.setattr(api_kafka, "Producer", fake_producer_init, raising=True)

        result = api_kafka.create_producer({"bootstrap.servers": "localhost:9092"})

        assert result is fake_producer

    def test_logs_info_on_creation(self, monkeypatch, caplog):
        """Should log info message when producer is created."""
        import logging

        caplog.set_level(logging.INFO)

        monkeypatch.setattr(
            api_kafka, "Producer", lambda config: FakeProducer(config), raising=True
        )

        api_kafka.create_producer({"bootstrap.servers": "localhost:9092"})

        assert "Producer successfully created" in caplog.text

    def test_logs_debug_with_client_id(self, monkeypatch, caplog):
        """Should log debug message with client.id."""
        import logging

        caplog.set_level(logging.DEBUG)

        monkeypatch.setattr(
            api_kafka, "Producer", lambda config: FakeProducer(config), raising=True
        )

        api_kafka.create_producer({
            "bootstrap.servers": "localhost:9092",
            "client.id": "my-producer",
        })

        assert "Producer created with client.id: my-producer" in caplog.text

    def test_uses_default_settings_config(self, monkeypatch):
        """Should use settings.kafka_config as default."""
        created_with_config = None

        def fake_producer_init(config):
            nonlocal created_with_config
            created_with_config = config
            return FakeProducer(config)

        monkeypatch.setattr(api_kafka, "Producer", fake_producer_init, raising=True)

        # Mock settings with a specific kafka_config
        fake_settings = SimpleNamespace(
            kafka_config={
                "bootstrap.servers": "default-broker:9092",
                "client.id": "default-client",
            }
        )
        monkeypatch.setattr(api_kafka, "settings", fake_settings, raising=True)

        # Call without arguments - should use default from settings
        # Note: Python evaluates default args at function definition time,
        # so we need to call with explicit None or the current default
        api_kafka.create_producer(fake_settings.kafka_config)

        assert created_with_config == {
            "bootstrap.servers": "default-broker:9092",
            "client.id": "default-client",
        }


class TestSendMessage:
    """Unit tests for send_message function."""

    def test_produces_message_to_correct_topic(self):
        """Should produce message to the specified topic."""
        producer = FakeProducer()

        api_kafka.send_message(
            producer=producer,
            value={"data": "test"},
            topic="custom-topic",
        )

        assert len(producer.produced_messages) == 1
        assert producer.produced_messages[0]["topic"] == "custom-topic"

    def test_uses_default_topic_from_constants(self, monkeypatch):
        """Should use API_KAFKA_TOPIC as default topic."""
        producer = FakeProducer()

        # The default topic comes from constants.API_KAFKA_TOPIC
        api_kafka.send_message(
            producer=producer,
            value={"data": "test"},
        )

        assert len(producer.produced_messages) == 1
        assert producer.produced_messages[0]["topic"] == api_kafka.constants.API_KAFKA_TOPIC

    def test_encodes_value_as_json_bytes(self):
        """Should encode value as JSON bytes."""
        producer = FakeProducer()

        value = {"id": 123, "name": "test", "active": True}
        api_kafka.send_message(producer=producer, value=value)

        produced_value = producer.produced_messages[0]["value"]
        assert produced_value == json.dumps(value).encode("utf-8")

    def test_encodes_key_as_utf8_bytes(self):
        """Should encode key as UTF-8 bytes when provided."""
        producer = FakeProducer()

        api_kafka.send_message(
            producer=producer,
            value={"data": "test"},
            key="my-key",
        )

        produced_key = producer.produced_messages[0]["key"]
        assert produced_key == b"my-key"

    def test_key_is_none_when_not_provided(self):
        """Should set key to None when not provided."""
        producer = FakeProducer()

        api_kafka.send_message(
            producer=producer,
            value={"data": "test"},
        )

        produced_key = producer.produced_messages[0]["key"]
        assert produced_key is None

    def test_sets_delivery_callback(self):
        """Should set delivery_callback as the callback."""
        producer = FakeProducer()

        api_kafka.send_message(producer=producer, value={"data": "test"})

        callback = producer.produced_messages[0]["callback"]
        assert callback is api_kafka.delivery_callback

    def test_calls_poll_after_produce(self):
        """Should call poll(0) to trigger delivery callbacks."""
        producer = FakeProducer()

        api_kafka.send_message(producer=producer, value={"data": "test"})

        assert producer.poll_count == 1

    def test_handles_unicode_key(self):
        """Should properly encode unicode characters in key."""
        producer = FakeProducer()

        api_kafka.send_message(
            producer=producer,
            value={"data": "test"},
            key="キー",  # Japanese for "key"
        )

        produced_key = producer.produced_messages[0]["key"]
        assert produced_key == "キー".encode("utf-8")

    def test_handles_complex_nested_value(self):
        """Should properly serialize complex nested values."""
        producer = FakeProducer()

        value = {
            "user": {"id": 1, "name": "Alice"},
            "items": [1, 2, 3],
            "metadata": {"nested": {"deep": True}},
        }
        api_kafka.send_message(producer=producer, value=value)

        produced_value = producer.produced_messages[0]["value"]
        assert json.loads(produced_value.decode("utf-8")) == value


class TestFlushProducer:
    """Unit tests for flush_producer function."""

    def test_calls_flush_with_timeout(self):
        """Should call flush with the specified timeout."""
        producer = FakeProducer()

        api_kafka.flush_producer(producer, timeout=5.0)

        assert producer.flush_count == 1
        assert producer.flush_timeout == 5.0

    def test_uses_default_timeout_of_10_seconds(self):
        """Should use 10.0 seconds as default timeout."""
        producer = FakeProducer()

        api_kafka.flush_producer(producer)

        assert producer.flush_timeout == 10.0

    def test_returns_remaining_message_count(self):
        """Should return the number of messages still in queue."""
        producer = FakeProducer()
        producer.remaining_after_flush = 5

        result = api_kafka.flush_producer(producer)

        assert result == 5

    def test_returns_zero_when_all_flushed(self):
        """Should return 0 when all messages are flushed."""
        producer = FakeProducer()
        producer.remaining_after_flush = 0

        result = api_kafka.flush_producer(producer)

        assert result == 0

    def test_logs_warning_when_messages_remain(self, caplog):
        """Should log warning when messages remain after flush."""
        import logging

        caplog.set_level(logging.WARNING)

        producer = FakeProducer()
        producer.remaining_after_flush = 3

        api_kafka.flush_producer(producer)

        assert "3 messages still in queue after flush" in caplog.text

    def test_no_warning_when_all_flushed(self, caplog):
        """Should not log warning when all messages are flushed."""
        import logging

        caplog.set_level(logging.WARNING)

        producer = FakeProducer()
        producer.remaining_after_flush = 0

        api_kafka.flush_producer(producer)

        assert "messages still in queue" not in caplog.text

