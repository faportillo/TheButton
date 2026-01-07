import logging
import time

import shared.constants as constants
from shared.kafka import create_producer, send_message
from shared.state import get_latest_state
from shared.rules import get_rules_by_hash
from shared.models import Phases
from watcher.config import settings
import uuid

logger = logging.getLogger(__name__)

PRODUCER = create_producer(settings.kafka_config)

def watcher_lambda(event, context):
    """This will update the state when no button presses occur, mainly checks for
    reductions in entropy in order to drop the phase down to a lower one without
    another user needing to click the button.
    
    Uses the rules version that matches the state's ruleshash to ensure consistency
    with the reducer that computed the current state.
    """
    state = get_latest_state()
    
    # Get rules matching the state's ruleshash to ensure consistency
    # This prevents race conditions if rules are updated while watcher is running
    _, rules_config = get_rules_by_hash(state["ruleshash"])

    timestamp_ms = int(time.time() * 1000)

    age = timestamp_ms - state["updated_at_ms"]
    current_phase = state["phase"]

    # Check cooldown for each phase and transition down if cooldown expired
    # Phase is stored as integer: 0=CALM, 1=WARM, 2=HOT, 3=CHAOS
    should_transition = False
    phase_name = "UNKNOWN"

    if current_phase == Phases.CHAOS.value:
        # CHAOS -> transition down if cooldown_chaos_ms expired
        if age >= rules_config.cooldown_chaos_ms:
            should_transition = True
            phase_name = "CHAOS"
    elif current_phase == Phases.HOT.value:
        # HOT -> transition down if cooldown_chaos_ms expired (HOT uses same cooldown as CHAOS)
        if age >= rules_config.cooldown_chaos_ms:
            should_transition = True
            phase_name = "HOT"
    elif current_phase == Phases.WARM.value:
        # WARM -> transition down if cooldown_warm_ms expired
        if age >= rules_config.cooldown_warm_ms:
            should_transition = True
            phase_name = "WARM"
    elif current_phase != Phases.CALM.value:
        # Any other non-CALM phase -> transition to CALM if cooldown_calm_ms expired
        if age >= rules_config.cooldown_calm_ms:
            should_transition = True
            phase_name = f"PHASE_{current_phase}"

    if should_transition:
        payload = {
            "timestamp_ms": timestamp_ms,
            "request_id": f"phase_transition:{timestamp_ms // 60}",
        }

        send_message(PRODUCER, value=payload, key=constants.API_KAFKA_GLOBAL_KEY)
        logger.info(
            f"Sent phase transition message for {phase_name} phase "
            f"(age={age}ms, cooldown expired)"
        )

    return {"success": True}


if __name__ == "__main__":
    logger.info("Watcher lambda started")
    logger.info(watcher_lambda({}, None))