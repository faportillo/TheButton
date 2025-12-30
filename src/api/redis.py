import redis
import logging
from api.config import settings
from shared.models import PersistedGlobalState
from shared.constants import API_REDIS_STATE_UPDATE_CHANNEL
from typing import AsyncGenerator
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


async def listen_on_pubsub(r: redis.Redis) -> AsyncGenerator[PersistedGlobalState]:
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)

    try:
        # listen() is itself a generator that blocks/waits for data
        async for message in p.listen():
            if message["type"] == "message":
                # Return type of message["data"] is str (if decode_responses=True)
                raw_data = message["data"]

                # Convert str to dict for processing
                data_dict = json.loads(raw_data)
                yield PersistedGlobalState(**data_dict)

    except (ConnectionError, TimeoutError) as e:
        # Handle transient production errors (log/alert)
        logger.error(f"Network issue detected: {e}. Stream interrupted.")
        # Add retry logic here

    except Exception as e:
        # Catch unexpected logic errors
        logger.error(f"Unexpected error in stream: {e}")
        raise

    finally:
        await p.unsubscribe(API_REDIS_STATE_UPDATE_CHANNEL)
        await p.close()
        await r.close()
