import redis
import logging
from reducer.config import settings
from shared.models import PersistedGlobalState
from shared.constants import REDUCER_REDIS_STATE_UPDATE_CHANNEL
import json

logger = logging.getLogger(__name__)


def create_redis_connection() -> redis.Redis:
    if settings.env == "prod":
        r = redis.from_url(**settings.redis_kwargs)
    elif settings.env == "dev":
        r = redis.Redis(**settings.redis_kwargs)
    else:
        raise ValueError("Env not recognized. Must use 'prod' or 'dev'")
    logger.info("Publisher connected to Redis")

    return r


def publish_state_update(r: redis.Redis, state: PersistedGlobalState):
    msg = {
        "type": "state_updated",
        "id": state.id,
        "last_applied_offset": state.last_applied_offset,
        "ruleshash": state.ruleshash,
    }
    r.publish(REDUCER_REDIS_STATE_UPDATE_CHANNEL, json.dumps(msg))
    logger.info(
        f"Published state update: id={state.id} offset={state.last_applied_offset}"
    )
