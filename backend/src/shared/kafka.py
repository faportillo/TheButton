from confluent_kafka import Producer, KafkaException
import logging
from typing import Dict, Union, Optional, Any
import shared.constants as constants
import json

logger = logging.getLogger(__name__)


def delivery_callback(err, msg):
    """Callback for message delivery confirmation."""
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")


def create_producer(
    config: Dict[str, Union[str, bool]]
) -> Producer:
    producer = Producer(config)
    logger.info("Producer successfully created")
    logger.debug(f"Producer created with client.id: {config.get('client.id')}")
    return producer


def send_message(
    producer: Producer,
    value: Dict[str, Any],
    key: Optional[str] = None,
    topic: str = constants.API_KAFKA_TOPIC,
) -> None:
    """Send a message to Kafka."""
    producer.produce(
        topic=topic,
        key=key.encode("utf-8") if key else None,
        value=json.dumps(value).encode("utf-8"),
        callback=delivery_callback,
    )
    # Trigger delivery callbacks
    producer.poll(0)


def flush_producer(producer: Producer, timeout: float = 10.0) -> int:
    """Flush pending messages. Returns number of messages still in queue."""
    remaining = producer.flush(timeout)
    if remaining > 0:
        logger.warning(f"{remaining} messages still in queue after flush")
    return remaining
