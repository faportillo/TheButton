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


def poll_batch_messages(consumer: Consumer, timeout: float = 0.1) -> Message:
    msgs: Message | None = consumer.poll(timeout)
    logger.debug(f"Successfully polled messages of len=={len(msgs)}")
    return msgs
