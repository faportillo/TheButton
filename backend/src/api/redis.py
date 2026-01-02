import redis
import redis.asyncio as aioredis
import logging
from api.config import settings
from shared.models import PersistedGlobalState
from shared.constants import API_REDIS_STATE_UPDATE_CHANNEL
from typing import AsyncGenerator
from datetime import datetime
import json

logger = logging.getLogger(__name__)


def create_redis_connection() -> redis.Redis:
    """Create a synchronous Redis connection (for rate limiting, health checks, etc.)"""
    if settings.env == "prod":
        r = redis.from_url(**settings.redis_kwargs)
    elif settings.env == "dev":
        r = redis.Redis(**settings.redis_kwargs)
    else:
        raise ValueError("Env not recognized. Must use 'prod' or 'dev'")
    logger.info("Sync Redis client connected")

    return r


def create_async_redis_connection() -> aioredis.Redis:
    """Create an async Redis connection (for SSE streaming)"""
    if settings.env == "prod" and settings.redis_url:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
    else:
        r = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            decode_responses=True,
        )
    logger.info("Async Redis client created")
    return r


async def listen_on_pubsub(r: redis.Redis) -> AsyncGenerator[PersistedGlobalState, None]:
    """
    Listen for state updates on Redis pubsub.
    
    Note: Creates its own async Redis connection for proper async iteration.
    The passed `r` parameter is ignored (kept for API compatibility).
    
    Yields:
        PersistedGlobalState from the reducer
    """
    # Create a fresh async Redis connection for this stream
    async_redis = create_async_redis_connection()
    p = async_redis.pubsub(ignore_subscribe_messages=True)
    
    try:
        await p.subscribe(API_REDIS_STATE_UPDATE_CHANNEL)
        logger.info(f"Subscribed to {API_REDIS_STATE_UPDATE_CHANNEL}")
        
        # listen() on async redis returns an async generator
        async for message in p.listen():
            if message["type"] == "message":
                # Return type of message["data"] is str (if decode_responses=True)
                raw_data = message["data"]

                # Convert str to dict for processing
                data_dict = json.loads(raw_data)
                
                # Parse ISO datetime string back to datetime object
                if data_dict.get("created_at"):
                    data_dict["created_at"] = datetime.fromisoformat(data_dict["created_at"])
                
                yield PersistedGlobalState(**data_dict)

    except (ConnectionError, TimeoutError) as e:
        # Handle transient production errors (log/alert)
        logger.error(f"Network issue detected: {e}. Stream interrupted.")

    except Exception as e:
        # Catch unexpected logic errors
        logger.error(f"Unexpected error in stream: {e}")
        raise

    finally:
        await p.unsubscribe(API_REDIS_STATE_UPDATE_CHANNEL)
        await p.close()
        await async_redis.close()
        logger.info("Pubsub connection closed")
