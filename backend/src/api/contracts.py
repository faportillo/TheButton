"""
Message contracts for inter-service communication.

These schemas define the structure of messages exchanged between services.
They serve as contracts that both producers and consumers must adhere to.

Changes to these schemas should be backwards-compatible to avoid breaking
downstream consumers.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timezone


class PressEventMessage(BaseModel):
    """
    Contract: Message produced by API when button is pressed.
    Consumer: Reducer service
    Topic: press_button

    This is the message format that the reducer expects to consume.
    """

    timestamp_ms: int = Field(
        ...,
        description="Unix timestamp in milliseconds when the press occurred",
        ge=0,
    )
    request_id: str = Field(
        ...,
        description="Unique identifier for this press request (UUID hex)",
        min_length=1,
        max_length=64,
    )

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        """Ensure request_id is a valid hex string."""
        if not v:
            raise ValueError("request_id cannot be empty")
        # Should be valid hex (UUID without dashes)
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("request_id must be a valid hex string")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timestamp_ms": 1704067200000,
                    "request_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                }
            ]
        }
    }


class StateUpdateMessage(BaseModel):
    """
    Contract: Message published by Reducer to notify of state changes.
    Consumer: API service (for SSE streaming)
    Channel: state_updates:v1 (Redis pub/sub)

    This is the message format that the API expects to receive via Redis pub/sub.
    """

    type: str = Field(
        default="state_updated",
        description="Message type identifier",
    )
    id: int = Field(
        ...,
        description="ID of the updated global state",
        ge=1,
    )
    last_applied_offset: int = Field(
        ...,
        description="Kafka offset of the last applied message",
        ge=0,
    )
    ruleshash: str = Field(
        ...,
        description="Hash of the ruleset used for this state",
        min_length=1,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "state_updated",
                    "id": 42,
                    "last_applied_offset": 1000,
                    "ruleshash": "abc123",
                }
            ]
        }
    }


class HealthStatus(BaseModel):
    """
    Contract: Health check response format.

    Standard format for health endpoints following common patterns.
    """

    status: str = Field(
        ...,
        description="Overall health status: 'healthy', 'degraded', or 'unhealthy'",
    )
    checks: dict[str, "ComponentHealth"] = Field(
        default_factory=dict,
        description="Individual component health checks",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the health check was performed",
    )


class ComponentHealth(BaseModel):
    """Health status of an individual component."""

    status: str = Field(
        ...,
        description="Component status: 'healthy' or 'unhealthy'",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Response time in milliseconds",
    )
    message: Optional[str] = Field(
        default=None,
        description="Additional status message or error details",
    )


# Update forward reference
HealthStatus.model_rebuild()

