from reducer.config import settings
from confluent_kafka import Consumer, Message
from shared.constants import REDUCER_KAFKA_TOPIC
from typing import Dict, Union
import logging

logger = logging.getLogger(__name__)


def create_consumer(
    config: Dict[str, Union[str, bool]] = settings.kafka_config,
) -> Consumer:
    consumer = Consumer(config)
    consumer.subscribe([REDUCER_KAFKA_TOPIC])
    logger.info("Consumer successfully created")
    logger.debug(
        f"Consumer created for GROUP ID:{settings.kafka_config['group.id']} and TOPIC: {REDUCER_KAFKA_TOPIC}"
    )

    return consumer


def poll_batch_messages(
    consumer: Consumer,
    batch_size: int = settings.kafka_max_batch_size,
    timeout: float = 1.0,
) -> list[Message]:
    """
    Poll for a batch of messages from Kafka.

    Args:
        consumer: Kafka consumer instance
        batch_size: Maximum number of messages to fetch
        timeout: Timeout in seconds for the consume operation

    Returns:
        List of messages (may be empty if no messages available)
    """
    msgs: list[Message] = consumer.consume(num_messages=batch_size, timeout=timeout)
    if msgs:
        logger.debug(f"Successfully polled {len(msgs)} messages")
    return msgs if msgs else []
