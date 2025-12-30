from reducer.config import settings
from consumer import create_consumer, poll_batch_messages
from notify import create_redis_connection, publish_state_update
from writer import write_state
from updater import apply_batch
from shared.models import PressEvent
from rules.retriever import get_latest_rules
import json
import logging
import time

logger = logging.getLogger(__name__)


def main():
    backoff_attempt = 0

    consumer = create_consumer()
    redis = create_redis_connection()
    ruleset, rules_config = get_latest_rules()
    try:
        while True:
            try:
                msgs = poll_batch_messages(consumer)
                if msgs is None or msgs == []:
                    continue

                if len(msgs) > 0:
                    events: list[PressEvent] = []
                    for msg in msgs:
                        payload = json.loads(msg.value())
                        events.append(
                            PressEvent(
                                offset=msg.offset(),
                                ts_ms=payload["ts_ms"],
                                request_id=payload["request_id"],
                            )
                        )

                    new_state = apply_batch(state, events, rules_config, ruleset.hash)
                    persisted_global_state = write_state(new_state)

                    try:
                        publish_state_update(redis, persisted_global_state)
                    except:
                        logger.warning(
                            "Redis publish failed — continuing without blocking reducer"
                        )

                    # commit up to the last offset in the batch
                    consumer.commit(asynchronous=False)
                    state = new_state

            except Exception as batch_err:
                if backoff_attempt >= settings.backoff_max_attempts:
                    logger.critical(
                        f"Reducer reached max attempts ({settings.backoff_max_attempts}) — crashing"
                    )
                    raise

                delay = min(
                    settings.max_backoff_seconds,
                    settings.backoff_base_seconds * (2**backoff_attempt),
                )
                logger.warning(
                    f"Error due to batch error: {batch_err}. Backing off {delay:.2f} sec"
                )
                time.sleep(delay)
                backoff_attempt += 1
                continue

    except KeyboardInterrupt:
        logger.info("Reducer shutting down gracefully...")

    finally:
        consumer.close()
        logger.info("Kafka consumer closed")
