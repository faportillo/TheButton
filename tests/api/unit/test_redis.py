import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from shared.models import PersistedGlobalState
import datetime
import json
import api.redis as api_redis


class FakeRedis:
    """A fake Redis client for testing."""

    def __init__(self):
        self.closed = False

    def pubsub(self, ignore_subscribe_messages=False):
        return FakePubSub(ignore_subscribe_messages)

    async def close(self):
        self.closed = True


class FakePubSub:
    """A fake PubSub object for testing."""

    def __init__(self, ignore_subscribe_messages=False):
        self.ignore_subscribe_messages = ignore_subscribe_messages
        self.subscribed_channels = []
        self.messages = []
        self.closed = False
        self.unsubscribed_channels = []

    def subscribe(self, channel):
        self.subscribed_channels.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed_channels.append(channel)

    async def close(self):
        self.closed = True

    def set_messages(self, messages):
        """Set messages to be returned by listen()."""
        self.messages = messages

    async def listen(self):
        """Async generator that yields messages."""
        for msg in self.messages:
            yield msg


class TestCreateRedisConnection:
    """Unit tests for create_redis_connection function."""

    def test_uses_from_url_in_prod(self, monkeypatch):
        """Should use redis.from_url when env is 'prod'."""
        fake_settings = SimpleNamespace(
            env="prod",
            redis_kwargs={"url": "redis://prod-host:6379/0"},
        )
        monkeypatch.setattr(api_redis, "settings", fake_settings, raising=True)

        fake_redis_instance = FakeRedis()

        class FakeRedisModule:
            @staticmethod
            def from_url(**kwargs):
                return fake_redis_instance

        monkeypatch.setattr(api_redis, "redis", FakeRedisModule(), raising=True)

        result = api_redis.create_redis_connection()

        assert result is fake_redis_instance

    def test_uses_redis_class_in_dev(self, monkeypatch):
        """Should use redis.Redis when env is 'dev'."""
        fake_settings = SimpleNamespace(
            env="dev",
            redis_kwargs={
                "host": "localhost",
                "port": 6379,
                "decode_responses": True,
            },
        )
        monkeypatch.setattr(api_redis, "settings", fake_settings, raising=True)

        fake_redis_instance = FakeRedis()

        class FakeRedisModule:
            @staticmethod
            def Redis(**kwargs):
                return fake_redis_instance

        monkeypatch.setattr(api_redis, "redis", FakeRedisModule(), raising=True)

        result = api_redis.create_redis_connection()

        assert result is fake_redis_instance

    def test_raises_value_error_for_unknown_env(self, monkeypatch):
        """Should raise ValueError when env is not 'prod' or 'dev'."""
        fake_settings = SimpleNamespace(
            env="staging",
            redis_kwargs={},
        )
        monkeypatch.setattr(api_redis, "settings", fake_settings, raising=True)

        with pytest.raises(ValueError, match="Env not recognized"):
            api_redis.create_redis_connection()

    def test_passes_redis_kwargs_to_from_url(self, monkeypatch):
        """Should pass redis_kwargs to redis.from_url in prod."""
        expected_kwargs = {
            "url": "redis://prod-host:6379/0",
            "health_check_interval": 10,
            "decode_responses": True,
        }
        fake_settings = SimpleNamespace(
            env="prod",
            redis_kwargs=expected_kwargs,
        )
        monkeypatch.setattr(api_redis, "settings", fake_settings, raising=True)

        received_kwargs = {}

        class FakeRedisModule:
            @staticmethod
            def from_url(**kwargs):
                nonlocal received_kwargs
                received_kwargs = kwargs
                return FakeRedis()

        monkeypatch.setattr(api_redis, "redis", FakeRedisModule(), raising=True)

        api_redis.create_redis_connection()

        assert received_kwargs == expected_kwargs

    def test_passes_redis_kwargs_to_redis_class(self, monkeypatch):
        """Should pass redis_kwargs to redis.Redis in dev."""
        expected_kwargs = {
            "host": "localhost",
            "port": 6379,
            "decode_responses": True,
        }
        fake_settings = SimpleNamespace(
            env="dev",
            redis_kwargs=expected_kwargs,
        )
        monkeypatch.setattr(api_redis, "settings", fake_settings, raising=True)

        received_kwargs = {}

        class FakeRedisModule:
            @staticmethod
            def Redis(**kwargs):
                nonlocal received_kwargs
                received_kwargs = kwargs
                return FakeRedis()

        monkeypatch.setattr(api_redis, "redis", FakeRedisModule(), raising=True)

        api_redis.create_redis_connection()

        assert received_kwargs == expected_kwargs


class TestListenOnPubsub:
    """Unit tests for listen_on_pubsub async generator."""

    @pytest.mark.asyncio
    async def test_subscribes_to_state_update_channel(self):
        """Should subscribe to the API_REDIS_STATE_UPDATE_CHANNEL."""
        subscribed_channels = []

        class MockPubSub:
            def subscribe(self, channel):
                subscribed_channels.append(channel)

            async def listen(self):
                return
                yield  # Make it a generator

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                pass

        class MockRedis:
            def pubsub(self, ignore_subscribe_messages=False):
                return MockPubSub()

            async def close(self):
                pass

        fake_redis = MockRedis()

        # Consume the generator
        async for _ in api_redis.listen_on_pubsub(fake_redis):
            pass

        assert api_redis.API_REDIS_STATE_UPDATE_CHANNEL in subscribed_channels

    @pytest.mark.asyncio
    async def test_yields_persisted_global_state_from_messages(self):
        """Should yield PersistedGlobalState from valid messages."""
        fake_redis = FakeRedis()

        state_data = {
            "id": 42,
            "last_applied_offset": 100,
            "ruleshash": "abc123",
            "created_at": "2025-01-01T00:00:00+00:00",
        }

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                yield {"type": "message", "data": json.dumps(state_data)}

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                pass

        fake_redis.pubsub = lambda ignore_subscribe_messages=False: MockPubSub()

        results = []
        async for state in api_redis.listen_on_pubsub(fake_redis):
            results.append(state)

        assert len(results) == 1
        assert isinstance(results[0], PersistedGlobalState)
        assert results[0].id == 42
        assert results[0].last_applied_offset == 100
        assert results[0].ruleshash == "abc123"

    @pytest.mark.asyncio
    async def test_ignores_non_message_types(self):
        """Should only yield from messages with type 'message'."""
        fake_redis = FakeRedis()

        state_data = {
            "id": 1,
            "last_applied_offset": 10,
            "ruleshash": "hash",
            "created_at": "2025-01-01T00:00:00+00:00",
        }

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                # Subscribe confirmation (should be ignored due to ignore_subscribe_messages)
                yield {"type": "subscribe", "data": 1}
                # Actual message
                yield {"type": "message", "data": json.dumps(state_data)}
                # Another non-message type
                yield {"type": "psubscribe", "data": 1}

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                pass

        fake_redis.pubsub = lambda ignore_subscribe_messages=False: MockPubSub()

        results = []
        async for state in api_redis.listen_on_pubsub(fake_redis):
            results.append(state)

        # Should only have one result from the actual message
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_yields_multiple_states(self):
        """Should yield multiple states from multiple messages."""
        fake_redis = FakeRedis()

        states = [
            {
                "id": 1,
                "last_applied_offset": 10,
                "ruleshash": "h1",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": 2,
                "last_applied_offset": 20,
                "ruleshash": "h2",
                "created_at": "2025-01-01T00:00:01+00:00",
            },
            {
                "id": 3,
                "last_applied_offset": 30,
                "ruleshash": "h3",
                "created_at": "2025-01-01T00:00:02+00:00",
            },
        ]

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                for s in states:
                    yield {"type": "message", "data": json.dumps(s)}

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                pass

        fake_redis.pubsub = lambda ignore_subscribe_messages=False: MockPubSub()

        results = []
        async for state in api_redis.listen_on_pubsub(fake_redis):
            results.append(state)

        assert len(results) == 3
        assert results[0].id == 1
        assert results[1].id == 2
        assert results[2].id == 3

    @pytest.mark.asyncio
    async def test_cleans_up_on_normal_exit(self):
        """Should unsubscribe and close connections on normal exit."""
        unsubscribed = []
        pubsub_closed = False
        redis_closed = False

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                # Empty generator - immediate exit
                return
                yield  # Make it a generator

            async def unsubscribe(self, channel):
                nonlocal unsubscribed
                unsubscribed.append(channel)

            async def close(self):
                nonlocal pubsub_closed
                pubsub_closed = True

        class MockRedis:
            def pubsub(self, ignore_subscribe_messages=False):
                return MockPubSub()

            async def close(self):
                nonlocal redis_closed
                redis_closed = True

        fake_redis = MockRedis()

        async for _ in api_redis.listen_on_pubsub(fake_redis):
            pass

        assert api_redis.API_REDIS_STATE_UPDATE_CHANNEL in unsubscribed
        assert pubsub_closed
        assert redis_closed

    @pytest.mark.asyncio
    async def test_logs_and_handles_connection_error(self, caplog):
        """Should log error on ConnectionError and clean up."""
        pubsub_closed = False
        redis_closed = False

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                raise ConnectionError("Connection lost")
                yield  # Make it a generator

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                nonlocal pubsub_closed
                pubsub_closed = True

        class MockRedis:
            def pubsub(self, ignore_subscribe_messages=False):
                return MockPubSub()

            async def close(self):
                nonlocal redis_closed
                redis_closed = True

        fake_redis = MockRedis()

        results = []
        async for state in api_redis.listen_on_pubsub(fake_redis):
            results.append(state)

        # Should have handled the error gracefully
        assert len(results) == 0
        assert pubsub_closed
        assert redis_closed

    @pytest.mark.asyncio
    async def test_logs_and_handles_timeout_error(self, caplog):
        """Should log error on TimeoutError and clean up."""
        pubsub_closed = False
        redis_closed = False

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                raise TimeoutError("Timed out")
                yield  # Make it a generator

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                nonlocal pubsub_closed
                pubsub_closed = True

        class MockRedis:
            def pubsub(self, ignore_subscribe_messages=False):
                return MockPubSub()

            async def close(self):
                nonlocal redis_closed
                redis_closed = True

        fake_redis = MockRedis()

        results = []
        async for state in api_redis.listen_on_pubsub(fake_redis):
            results.append(state)

        assert len(results) == 0
        assert pubsub_closed
        assert redis_closed

    @pytest.mark.asyncio
    async def test_raises_unexpected_exceptions(self):
        """Should re-raise unexpected exceptions after cleanup."""
        pubsub_closed = False
        redis_closed = False

        class MockPubSub:
            def __init__(self):
                self.subscribed_channels = []

            def subscribe(self, channel):
                self.subscribed_channels.append(channel)

            async def listen(self):
                raise ValueError("Unexpected error")
                yield  # Make it a generator

            async def unsubscribe(self, channel):
                pass

            async def close(self):
                nonlocal pubsub_closed
                pubsub_closed = True

        class MockRedis:
            def pubsub(self, ignore_subscribe_messages=False):
                return MockPubSub()

            async def close(self):
                nonlocal redis_closed
                redis_closed = True

        fake_redis = MockRedis()

        with pytest.raises(ValueError, match="Unexpected error"):
            async for _ in api_redis.listen_on_pubsub(fake_redis):
                pass

        # Cleanup should still happen
        assert pubsub_closed
        assert redis_closed

