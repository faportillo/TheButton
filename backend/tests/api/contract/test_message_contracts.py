"""
Contract tests for message schemas.

These tests verify that:
1. Messages conform to expected schemas
2. Schema validation catches invalid data
3. Serialization/deserialization is consistent
4. Breaking changes are detected

Run these tests before deploying to catch contract violations.
"""

import pytest
import json
import time
import uuid
from pydantic import ValidationError
from api.contracts import (
    PressEventMessage,
    StateUpdateMessage,
    HealthStatus,
    ComponentHealth,
)


class TestPressEventMessageContract:
    """Contract tests for PressEventMessage (API → Reducer)."""

    def test_valid_press_event(self):
        """Should accept a valid press event."""
        event = PressEventMessage(
            timestamp_ms=int(time.time() * 1000),
            request_id=uuid.uuid4().hex,
        )

        assert event.timestamp_ms > 0
        assert len(event.request_id) == 32  # UUID hex is 32 chars

    def test_serialization_matches_api_format(self):
        """Should serialize to format expected by reducer."""
        event = PressEventMessage(
            timestamp_ms=1704067200000,
            request_id="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        )

        json_str = event.model_dump_json()
        parsed = json.loads(json_str)

        # Verify exact field names (reducer expects these)
        assert "timestamp_ms" in parsed
        assert "request_id" in parsed
        assert parsed["timestamp_ms"] == 1704067200000
        assert parsed["request_id"] == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

    def test_rejects_negative_timestamp(self):
        """Should reject negative timestamps."""
        with pytest.raises(ValidationError) as exc_info:
            PressEventMessage(
                timestamp_ms=-1,
                request_id="abc123",
            )

        errors = exc_info.value.errors()
        assert any("timestamp_ms" in str(e) for e in errors)

    def test_rejects_empty_request_id(self):
        """Should reject empty request_id."""
        with pytest.raises(ValidationError) as exc_info:
            PressEventMessage(
                timestamp_ms=1704067200000,
                request_id="",
            )

        errors = exc_info.value.errors()
        assert any("request_id" in str(e) for e in errors)

    def test_rejects_non_hex_request_id(self):
        """Should reject non-hex request_id."""
        with pytest.raises(ValidationError) as exc_info:
            PressEventMessage(
                timestamp_ms=1704067200000,
                request_id="not-a-hex-string!",
            )

        errors = exc_info.value.errors()
        assert any("request_id" in str(e) for e in errors)

    def test_round_trip_serialization(self):
        """Should survive JSON round-trip."""
        original = PressEventMessage(
            timestamp_ms=1704067200000,
            request_id="abcdef1234567890abcdef1234567890",
        )

        json_str = original.model_dump_json()
        restored = PressEventMessage.model_validate_json(json_str)

        assert restored.timestamp_ms == original.timestamp_ms
        assert restored.request_id == original.request_id

    def test_deserialization_from_dict(self):
        """Should deserialize from dict (as received from Kafka)."""
        raw_message = {
            "timestamp_ms": 1704067200000,
            "request_id": "abc123def456abc123def456abc123de",
        }

        event = PressEventMessage.model_validate(raw_message)

        assert event.timestamp_ms == 1704067200000
        assert event.request_id == "abc123def456abc123def456abc123de"


class TestStateUpdateMessageContract:
    """Contract tests for StateUpdateMessage (Reducer → API)."""

    def test_valid_state_update(self):
        """Should accept a valid state update."""
        update = StateUpdateMessage(
            id=42,
            last_applied_offset=1000,
            ruleshash="abc123",
        )

        assert update.type == "state_updated"
        assert update.id == 42
        assert update.last_applied_offset == 1000

    def test_serialization_matches_reducer_format(self):
        """Should serialize to format expected by API."""
        update = StateUpdateMessage(
            id=42,
            last_applied_offset=1000,
            ruleshash="abc123",
        )

        json_str = update.model_dump_json()
        parsed = json.loads(json_str)

        # Verify exact field names (API expects these)
        assert parsed["type"] == "state_updated"
        assert parsed["id"] == 42
        assert parsed["last_applied_offset"] == 1000
        assert parsed["ruleshash"] == "abc123"

    def test_rejects_zero_id(self):
        """Should reject id of 0 (IDs start at 1)."""
        with pytest.raises(ValidationError) as exc_info:
            StateUpdateMessage(
                id=0,
                last_applied_offset=100,
                ruleshash="hash",
            )

        errors = exc_info.value.errors()
        assert any("id" in str(e) for e in errors)

    def test_rejects_negative_offset(self):
        """Should reject negative offsets."""
        with pytest.raises(ValidationError) as exc_info:
            StateUpdateMessage(
                id=1,
                last_applied_offset=-1,
                ruleshash="hash",
            )

        errors = exc_info.value.errors()
        assert any("last_applied_offset" in str(e) for e in errors)

    def test_rejects_empty_ruleshash(self):
        """Should reject empty ruleshash."""
        with pytest.raises(ValidationError) as exc_info:
            StateUpdateMessage(
                id=1,
                last_applied_offset=100,
                ruleshash="",
            )

        errors = exc_info.value.errors()
        assert any("ruleshash" in str(e) for e in errors)

    def test_round_trip_serialization(self):
        """Should survive JSON round-trip."""
        original = StateUpdateMessage(
            id=42,
            last_applied_offset=1000,
            ruleshash="abc123def",
        )

        json_str = original.model_dump_json()
        restored = StateUpdateMessage.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.last_applied_offset == original.last_applied_offset
        assert restored.ruleshash == original.ruleshash

    def test_deserialization_from_redis_message(self):
        """Should deserialize from dict (as received from Redis)."""
        raw_message = {
            "type": "state_updated",
            "id": 100,
            "last_applied_offset": 5000,
            "ruleshash": "xyz789",
        }

        update = StateUpdateMessage.model_validate(raw_message)

        assert update.type == "state_updated"
        assert update.id == 100
        assert update.last_applied_offset == 5000


class TestHealthStatusContract:
    """Contract tests for HealthStatus response format."""

    def test_healthy_status(self):
        """Should create healthy status."""
        status = HealthStatus(
            status="healthy",
            checks={
                "redis": ComponentHealth(status="healthy", latency_ms=1.5),
                "kafka": ComponentHealth(status="healthy", latency_ms=3.2),
            },
        )

        assert status.status == "healthy"
        assert len(status.checks) == 2

    def test_unhealthy_status_with_message(self):
        """Should include error message for unhealthy components."""
        status = HealthStatus(
            status="unhealthy",
            checks={
                "redis": ComponentHealth(
                    status="unhealthy",
                    message="Connection refused",
                ),
            },
        )

        assert status.status == "unhealthy"
        assert status.checks["redis"].message == "Connection refused"

    def test_serialization_format(self):
        """Should serialize to expected JSON format."""
        status = HealthStatus(
            status="healthy",
            checks={
                "redis": ComponentHealth(status="healthy", latency_ms=1.0),
            },
        )

        data = status.model_dump()

        assert data["status"] == "healthy"
        assert "checks" in data
        assert "redis" in data["checks"]
        assert data["checks"]["redis"]["status"] == "healthy"
        assert data["checks"]["redis"]["latency_ms"] == 1.0


class TestBackwardsCompatibility:
    """Tests to ensure backwards compatibility of contracts."""

    def test_press_event_extra_fields_ignored(self):
        """Should ignore extra fields (for forward compatibility)."""
        # Simulate a message from a newer version with extra fields
        raw_message = {
            "timestamp_ms": 1704067200000,
            "request_id": "abc123def456abc123def456abc123de",
            "new_field": "should be ignored",
            "another_new_field": 123,
        }

        # Should not raise, extra fields ignored
        event = PressEventMessage.model_validate(raw_message)

        assert event.timestamp_ms == 1704067200000
        assert event.request_id == "abc123def456abc123def456abc123de"

    def test_state_update_extra_fields_ignored(self):
        """Should ignore extra fields (for forward compatibility)."""
        raw_message = {
            "type": "state_updated",
            "id": 1,
            "last_applied_offset": 100,
            "ruleshash": "hash",
            "future_field": {"nested": "data"},
        }

        update = StateUpdateMessage.model_validate(raw_message)

        assert update.id == 1
        assert update.ruleshash == "hash"

    def test_press_event_required_fields(self):
        """Document required fields - removing these would break consumers."""
        required_fields = {"timestamp_ms", "request_id"}

        schema = PressEventMessage.model_json_schema()
        actual_required = set(schema.get("required", []))

        assert required_fields == actual_required, (
            f"Required fields changed! Expected {required_fields}, got {actual_required}. "
            "This is a breaking change for consumers."
        )

    def test_state_update_required_fields(self):
        """Document required fields - removing these would break consumers."""
        required_fields = {"id", "last_applied_offset", "ruleshash"}

        schema = StateUpdateMessage.model_json_schema()
        actual_required = set(schema.get("required", []))

        assert required_fields == actual_required, (
            f"Required fields changed! Expected {required_fields}, got {actual_required}. "
            "This is a breaking change for consumers."
        )

