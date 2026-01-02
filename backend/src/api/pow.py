"""
Proof-of-Work (PoW) challenge system for anti-abuse protection.

Requires clients to compute a hash with leading zeros before submitting
requests. This makes automated abuse expensive while barely affecting
legitimate users.

Flow:
1. Client requests challenge from /v1/challenge
2. Client finds nonce where SHA256(challenge + nonce) has N leading hex zeros
3. Client submits request with challenge + nonce
4. Server verifies solution (single hash) and marks challenge as used

Dev Mode:
- Set POW_BYPASS=true to skip PoW verification (for Swagger/manual testing)
- Or use difficulty=0 challenges which accept any nonce
"""

import hashlib
import hmac
import os
import secrets
import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from redis import Redis

logger = logging.getLogger(__name__)

# =============================================================================
# Dev Mode Bypass
# =============================================================================

# Set POW_BYPASS=true in environment to skip PoW verification entirely
POW_BYPASS = os.getenv("POW_BYPASS", "false").lower() in ("true", "1", "yes")


# =============================================================================
# Configuration
# =============================================================================

# Number of leading hex zeros required (4 = ~65k hashes, ~50-100ms on phone)
DEFAULT_DIFFICULTY = 4

# How long a challenge is valid (seconds)
CHALLENGE_TTL_SECONDS = 30

# Secret key for HMAC signing challenges (prevents client from forging)
# In production, load this from environment/secrets manager
POW_SECRET_KEY = secrets.token_bytes(32)

# Redis key prefix for used challenges
USED_CHALLENGE_PREFIX = "pow:used:"


@dataclass
class Challenge:
    """A PoW challenge issued to a client."""
    challenge_id: str  # Random unique ID
    difficulty: int  # Number of leading zeros required
    expires_at: int  # Unix timestamp (seconds)
    signature: str  # HMAC signature to prevent tampering

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "difficulty": self.difficulty,
            "expires_at": self.expires_at,
            "signature": self.signature,
        }


@dataclass
class Solution:
    """A PoW solution submitted by client."""
    challenge_id: str
    difficulty: int
    expires_at: int
    signature: str
    nonce: str  # The solution found by client


# =============================================================================
# Challenge Generation
# =============================================================================


def _sign_challenge(challenge_id: str, difficulty: int, expires_at: int) -> str:
    """Create HMAC signature for challenge to prevent tampering."""
    message = f"{challenge_id}:{difficulty}:{expires_at}".encode()
    return hmac.new(POW_SECRET_KEY, message, hashlib.sha256).hexdigest()


def generate_challenge(difficulty: int = DEFAULT_DIFFICULTY) -> Challenge:
    """
    Generate a new PoW challenge.
    
    Args:
        difficulty: Number of leading hex zeros required in solution hash
        
    Returns:
        Challenge object with signed parameters
    """
    challenge_id = secrets.token_hex(16)  # 32 char random string
    expires_at = int(time.time()) + CHALLENGE_TTL_SECONDS
    signature = _sign_challenge(challenge_id, difficulty, expires_at)
    
    return Challenge(
        challenge_id=challenge_id,
        difficulty=difficulty,
        expires_at=expires_at,
        signature=signature,
    )


# =============================================================================
# Solution Verification
# =============================================================================


def _verify_signature(solution: Solution) -> bool:
    """Verify the challenge wasn't tampered with."""
    expected = _sign_challenge(
        solution.challenge_id,
        solution.difficulty,
        solution.expires_at
    )
    return hmac.compare_digest(expected, solution.signature)


def _check_hash_difficulty(hash_hex: str, difficulty: int) -> bool:
    """Check if hash has required number of leading zeros."""
    return hash_hex.startswith("0" * difficulty)


def _compute_solution_hash(challenge_id: str, nonce: str) -> str:
    """Compute the hash that the client should have found."""
    data = f"{challenge_id}:{nonce}".encode()
    return hashlib.sha256(data).hexdigest()


def _is_challenge_used(redis_client: Redis, challenge_id: str) -> bool:
    """Check if a challenge has already been used (replay protection)."""
    try:
        key = f"{USED_CHALLENGE_PREFIX}{challenge_id}"
        return redis_client.exists(key) > 0
    except Exception as e:
        logger.warning(f"Failed to check challenge usage: {e}")
        # Fail open - don't block if Redis is down
        return False


def _mark_challenge_used(redis_client: Redis, challenge_id: str, ttl: int) -> None:
    """Mark a challenge as used to prevent replay attacks."""
    try:
        key = f"{USED_CHALLENGE_PREFIX}{challenge_id}"
        redis_client.setex(key, ttl, "1")
    except Exception as e:
        logger.warning(f"Failed to mark challenge as used: {e}")


def verify_solution(
    redis_client: Redis,
    solution: Solution
) -> Tuple[bool, Optional[str]]:
    """
    Verify a PoW solution.
    
    Checks:
    1. Signature is valid (challenge wasn't tampered)
    2. Challenge hasn't expired
    3. Challenge hasn't been used before (replay protection)
    4. Hash has required leading zeros
    
    Args:
        redis_client: Redis connection for replay protection
        solution: The solution submitted by client
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Dev mode bypass - skip all verification
    if POW_BYPASS:
        logger.warning("PoW bypass enabled - skipping verification (dev mode)")
        return True, None
    
    # 1. Verify signature (challenge wasn't forged/tampered)
    if not _verify_signature(solution):
        logger.warning(f"Invalid signature for challenge {solution.challenge_id}")
        return False, "Invalid challenge signature"
    
    # 2. Check expiration
    now = int(time.time())
    if now > solution.expires_at:
        logger.debug(f"Expired challenge {solution.challenge_id}")
        return False, "Challenge expired"
    
    # 3. Check replay (challenge already used)
    if _is_challenge_used(redis_client, solution.challenge_id):
        logger.warning(f"Replay attempt for challenge {solution.challenge_id}")
        return False, "Challenge already used"
    
    # 4. Verify the actual PoW solution
    solution_hash = _compute_solution_hash(solution.challenge_id, solution.nonce)
    if not _check_hash_difficulty(solution_hash, solution.difficulty):
        logger.warning(
            f"Invalid PoW for challenge {solution.challenge_id}: "
            f"hash {solution_hash[:16]}... doesn't have {solution.difficulty} leading zeros"
        )
        return False, "Invalid proof of work"
    
    # Solution is valid - mark as used
    remaining_ttl = solution.expires_at - now + 5  # Small buffer
    _mark_challenge_used(redis_client, solution.challenge_id, remaining_ttl)
    
    logger.debug(f"Valid PoW solution for challenge {solution.challenge_id}")
    return True, None


# =============================================================================
# Utility for testing/client reference
# =============================================================================


def solve_challenge(challenge: Challenge) -> str:
    """
    Solve a PoW challenge (for testing or reference implementation).
    
    This is what the client needs to do:
    - Try nonces until SHA256(challenge_id + nonce) has required leading zeros
    
    Args:
        challenge: The challenge to solve
        
    Returns:
        The nonce that solves the challenge
    """
    nonce = 0
    target = "0" * challenge.difficulty
    
    while True:
        nonce_str = str(nonce)
        hash_result = _compute_solution_hash(challenge.challenge_id, nonce_str)
        
        if hash_result.startswith(target):
            return nonce_str
        
        nonce += 1

