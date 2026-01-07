import logging
import time

import shared.constants as constants
from shared.kafka import create_producer, send_message
from shared.state import get_latest_state
from watcher.config import settings
import uuid

logger = logging.getLogger(__name__)

PRODUCER = create_producer(settings.kafka_config)

def watcher_lambda(event, context):
    """This will update the state when no button presses occur, mainly checks for
    reductions in entropy in order to drop the phase down to a lower one without
    another user needing to click the button.
    """
    state = get_latest_state()

    timestamp_ms = int(time.time() * 1000)

    age = timestamp_ms - state["updated_at_ms"]

    if state["phase"] != "CALM" and age >= state["cooldown_calm_ms"]:
        payload = {
            "ts": timestamp_ms,
            "request_id": f"phase_transition:{timestamp_ms // 60}",
        }        

        send_message(PRODUCER, value=payload, key=constants.API_KAFKA_GLOBAL_KEY)

    return {"success": True}


if __name__ == "__main__":
    logger.info("Watcher lambda started")
    logger.info(watcher_lambda({}, None))