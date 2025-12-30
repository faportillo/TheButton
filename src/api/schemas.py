from pydantic import BaseModel
from uuid import UUID
from enum import Enum
from typing import Optional
from datetime import datetime


class Phase(Enum):
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4


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
