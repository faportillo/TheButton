from pydantic import BaseModel, Field
from uuid import UUID
from enum import Enum
from typing import Optional
from datetime import datetime


class Phase(Enum):
    CALM = 0
    WARM = 1
    HOT = 2
    CHAOS = 3


class GlobalState(BaseModel):
    id: int
    last_applied_offset: int
    counter: int
    phase: Phase
    entropy: float
    reveal_until_ms: int
    cooldown_ms: Optional[int]
    updated_at_ms: int
    created_at: datetime

    class Config:
        orm_mode = True


class PressResponse(BaseModel):
    request_id: str
    timestamp_ms: int


class ErrorResponse(BaseModel):
    detail: str


# =============================================================================
# Proof-of-Work Schemas
# =============================================================================


class ChallengeResponse(BaseModel):
    """PoW challenge issued to client."""
    challenge_id: str = Field(..., description="Unique challenge identifier")
    difficulty: int = Field(..., description="Number of leading hex zeros required")
    expires_at: int = Field(..., description="Unix timestamp when challenge expires")
    signature: str = Field(..., description="HMAC signature (include in solution)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "challenge_id": "a1b2c3d4e5f6789012345678",
                "difficulty": 4,
                "expires_at": 1735500000,
                "signature": "abc123..."
            }
        }


class PressRequest(BaseModel):
    """Button press request with PoW solution."""
    challenge_id: str = Field(..., description="Challenge ID from /v1/challenge")
    difficulty: int = Field(..., description="Difficulty from challenge")
    expires_at: int = Field(..., description="Expiration from challenge")
    signature: str = Field(..., description="Signature from challenge")
    nonce: str = Field(..., description="Nonce that solves the challenge")
    
    class Config:
        json_schema_extra = {
            "example": {
                "challenge_id": "a1b2c3d4e5f6789012345678",
                "difficulty": 4,
                "expires_at": 1735500000,
                "signature": "abc123...",
                "nonce": "48291"
            }
        }
