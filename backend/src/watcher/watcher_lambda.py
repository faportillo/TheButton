from reducer.writer import get_latest_state, write_state
from shared.models import WatcherEvent
from shared.state import get_latest_state
from reducer.updater import apply_event
from watcher.config import settings
import time
import redis
import logging

logger = logging.getLogger(__name__)


def watcher_lambda():
    """This will update the state when no button presses occur, mainly checks for
    reductions in entropy in order to drop the phase down to a lower one without
    another user needing to click the button.
    """
    state = get_latest_state()

    now_timestamp_ms = time.time() / 1000

    watcher_event = WatcherEvent(timestamp_ms=now_timestamp_ms)

    


if __name__ == "__main__":
    redis = create_redis_connection()
    ruleset, rules_config = get_rules_by_hash(settings.rules_hash)

    state_watcher(redis, rules_config, ruleset.hash)
