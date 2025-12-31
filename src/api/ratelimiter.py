"""
IP-based rate limiting for open/unauthenticated API endpoints.

Uses Redis sliding window algorithm for distributed rate limiting across
multiple API instances. Includes:
- Multi-tier limits (burst + sustained)
- Real IP extraction from proxy headers
- IP blocklist for known bad actors
- Proper 429 responses with Retry-After headers
"""

import time
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from fastapi import Request, HTTPException, status
from redis import Redis

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit tier."""
    requests: int  # Max requests allowed
    window_seconds: int  # Time window in seconds
    key_prefix: str  # Redis key prefix for this tier


# Default rate limit tiers
BURST_LIMIT = RateLimitConfig(
    requests=10,
    window_seconds=1,
    key_prefix="rl:burst"
)

SUSTAINED_LIMIT = RateLimitConfig(
    requests=60,
    window_seconds=60,
    key_prefix="rl:sustained"
)

# Stricter limits for the press endpoint specifically
PRESS_BURST_LIMIT = RateLimitConfig(
    requests=5,
    window_seconds=1,
    key_prefix="rl:press:burst"
)

PRESS_SUSTAINED_LIMIT = RateLimitConfig(
    requests=30,
    window_seconds=60,
    key_prefix="rl:press:sustained"
)


# Redis key for IP blocklist (a Redis Set)
BLOCKLIST_KEY = "rl:blocklist"


def get_real_ip(request: Request) -> str:
    """
    Extract the real client IP address from the request.
    
    Handles common proxy headers in order of preference:
    1. CF-Connecting-IP (Cloudflare)
    2. X-Real-IP (nginx, common convention)
    3. X-Forwarded-For (standard proxy header, take first IP)
    4. Fall back to direct client IP
    
    Note: In production, configure your reverse proxy to set these
    headers and trust only your proxy's headers to prevent spoofing.
    """
    # Cloudflare
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    
    # X-Real-IP (commonly set by nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # X-Forwarded-For: client, proxy1, proxy2, ...
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first (leftmost) IP, which is the original client
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip
    
    # Fall back to direct connection IP
    if request.client:
        return request.client.host
    
    return "unknown"


def is_ip_blocked(redis_client: Redis, ip: str) -> bool:
    """Check if an IP is in the blocklist."""
    try:
        return redis_client.sismember(BLOCKLIST_KEY, ip)
    except Exception as e:
        logger.warning(f"Failed to check blocklist for {ip}: {e}")
        # Fail open - don't block if Redis is down
        return False


def block_ip(redis_client: Redis, ip: str, reason: str = "") -> bool:
    """Add an IP to the blocklist."""
    try:
        redis_client.sadd(BLOCKLIST_KEY, ip)
        logger.warning(f"Blocked IP {ip}: {reason}")
        return True
    except Exception as e:
        logger.error(f"Failed to block IP {ip}: {e}")
        return False


def unblock_ip(redis_client: Redis, ip: str) -> bool:
    """Remove an IP from the blocklist."""
    try:
        redis_client.srem(BLOCKLIST_KEY, ip)
        logger.info(f"Unblocked IP {ip}")
        return True
    except Exception as e:
        logger.error(f"Failed to unblock IP {ip}: {e}")
        return False


def check_rate_limit(
    redis_client: Redis,
    ip: str,
    config: RateLimitConfig
) -> Tuple[bool, int, int]:
    """
    Check if request is within rate limit using sliding window algorithm.
    
    Uses Redis sorted sets with timestamps as scores for accurate
    sliding window rate limiting.
    
    Args:
        redis_client: Redis connection
        ip: Client IP address
        config: Rate limit configuration
    
    Returns:
        Tuple of (allowed, remaining, retry_after_seconds)
        - allowed: True if request should be allowed
        - remaining: Number of requests remaining in window
        - retry_after: Seconds until the client can retry (0 if allowed)
    """
    key = f"{config.key_prefix}:{ip}"
    now = time.time()
    window_start = now - config.window_seconds
    
    try:
        pipe = redis_client.pipeline()
        
        # Remove expired entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in window
        pipe.zcard(key)
        
        # Get oldest entry to calculate retry-after
        pipe.zrange(key, 0, 0, withscores=True)
        
        results = pipe.execute()
        current_count = results[1]
        oldest_entry = results[2]
        
        if current_count >= config.requests:
            # Rate limit exceeded
            retry_after = 1  # Default retry
            if oldest_entry:
                # Calculate when the oldest request will expire
                oldest_time = oldest_entry[0][1]
                retry_after = max(1, int((oldest_time + config.window_seconds) - now) + 1)
            
            remaining = 0
            logger.debug(f"Rate limit exceeded for {ip} on {config.key_prefix}")
            return False, remaining, retry_after
        
        # Request allowed - add it to the window
        pipe2 = redis_client.pipeline()
        pipe2.zadd(key, {f"{now}": now})
        pipe2.expire(key, config.window_seconds + 1)  # TTL slightly longer than window
        pipe2.execute()
        
        remaining = config.requests - current_count - 1
        return True, remaining, 0
        
    except Exception as e:
        logger.warning(f"Rate limit check failed for {ip}: {e}")
        # Fail open - allow request if Redis is down
        return True, config.requests, 0


def check_rate_limits(
    redis_client: Redis,
    ip: str,
    limits: list[RateLimitConfig]
) -> Tuple[bool, int, int, Optional[RateLimitConfig]]:
    """
    Check multiple rate limit tiers.
    
    Returns on first limit exceeded, or allows if all pass.
    
    Returns:
        Tuple of (allowed, remaining, retry_after, violated_limit)
    """
    for limit in limits:
        allowed, remaining, retry_after = check_rate_limit(redis_client, ip, limit)
        if not allowed:
            return False, remaining, retry_after, limit
    
    # All limits passed - return remaining from the most restrictive (last) limit
    return True, remaining, 0, None


def rate_limit_request(
    request: Request,
    redis_client: Redis,
    limits: list[RateLimitConfig] = None
) -> str:
    """
    Apply rate limiting to a request. Raises HTTPException if limited.
    
    Args:
        request: FastAPI request object
        redis_client: Redis connection
        limits: List of rate limit configs to apply (default: burst + sustained)
    
    Returns:
        The client IP address
    
    Raises:
        HTTPException 403: If IP is blocklisted
        HTTPException 429: If rate limit exceeded
    """
    if limits is None:
        limits = [BURST_LIMIT, SUSTAINED_LIMIT]
    
    ip = get_real_ip(request)
    
    # Check blocklist first
    if is_ip_blocked(redis_client, ip):
        logger.warning(f"Blocked IP attempted access: {ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Check rate limits
    allowed, remaining, retry_after, violated = check_rate_limits(
        redis_client, ip, limits
    )
    
    if not allowed:
        logger.info(
            f"Rate limit {violated.key_prefix} exceeded for {ip}, "
            f"retry after {retry_after}s"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(violated.requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + retry_after),
            }
        )
    
    return ip


def rate_limit_press(request: Request, redis_client: Redis) -> str:
    """
    Apply stricter rate limiting for the press endpoint.
    
    This is the main action endpoint and needs tighter controls
    to prevent abuse.
    """
    return rate_limit_request(
        request,
        redis_client,
        limits=[PRESS_BURST_LIMIT, PRESS_SUSTAINED_LIMIT]
    )

