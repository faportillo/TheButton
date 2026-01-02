import pytest
import reducer.notify as notify
from types import SimpleNamespace
from shared.models import PersistedGlobalState
import datetime


class _FakeRedis:
    def __init__(self):
        self.publishes = []

    def publish(self, channel, message):
        self.publishes.append((channel, message))
        return 1


def test_create_redis_connection_uses_url_in_prod(monkeypatch):
    fake_settings = SimpleNamespace(
        env="prod",
        redis_kwargs={"url": "redis://localhost:6379/0"},
    )
    monkeypatch.setattr(notify, "settings", fake_settings, raising=True)

    # Monkeypatch redis module used by notify
    class _RedisModule:
        @staticmethod
        def from_url(**kwargs):
            return _FakeRedis()

    monkeypatch.setattr(notify, "redis", _RedisModule(), raising=True)
    r = notify.create_redis_connection()
    assert isinstance(r, _FakeRedis)


def test_publish_state_update_publishes_json(monkeypatch):
    r = _FakeRedis()
    state = PersistedGlobalState(
        id=1,
        last_applied_offset=10,
        ruleshash="h",
        created_at=datetime.datetime.now(datetime.UTC),
    )
    notify.publish_state_update(r, state)
    assert len(r.publishes) == 1
    channel, message = r.publishes[0]
    assert channel == notify.REDUCER_REDIS_STATE_UPDATE_CHANNEL
    import json

    msg = json.loads(message)
    assert msg == {
        "id": 1,
        "last_applied_offset": 10,
        "ruleshash": "h",
        "created_at": state.created_at.isoformat(),
    }
