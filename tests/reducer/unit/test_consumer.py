import types
import reducer.consumer as consumer_mod
from shared.constants import REDUCER_KAFKA_TOPIC


class _FakeConsumer:
    def __init__(self, config):
        self.config = config
        self.subscriptions = []
        self.polled = []
        self.consumed = []

    def subscribe(self, topics):
        self.subscriptions.extend(topics)

    def poll(self, timeout):
        self.polled.append(timeout)
        return []

    def consume(self, num_messages=1, timeout=1.0):
        self.consumed.append((num_messages, timeout))
        return []


def test_create_consumer_subscribes(monkeypatch):
    fake = _FakeConsumer
    monkeypatch.setattr(consumer_mod, "Consumer", fake)

    c = consumer_mod.create_consumer()
    assert isinstance(c, _FakeConsumer)
    assert REDUCER_KAFKA_TOPIC in c.subscriptions


def test_poll_batch_messages_calls_poll(monkeypatch):
    fake = _FakeConsumer({})
    res = consumer_mod.poll_batch_messages(fake, timeout=0.25)
    assert res == []
