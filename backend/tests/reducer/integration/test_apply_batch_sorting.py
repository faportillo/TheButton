import pytest
from dataclasses import dataclass
from typing import Optional

from shared.models import (
    CreateGlobalStateEntity,
    GlobalStateEntity,
    PressEvent,
    RulesConfig,
)
import reducer.updater as updater


@dataclass(frozen=True)
class _State(GlobalStateEntity):
    pass


def _make_state() -> GlobalStateEntity:
    return GlobalStateEntity(
        id=1,
        last_applied_offset=0,
        updated_at_ms=0,
        ruleshash="hash",
        counter=0,
        phase=0,
        entropy=0,
        reveal_until_ms=0,
        cooldown_ms=None,
    )


def _make_event(offset: int, ts: int) -> PressEvent:
    return PressEvent(offset=offset, timestamp_ms=ts, request_id=f"r-{offset}")


def test_apply_batch_sorts_by_offset(
    monkeypatch: pytest.MonkeyPatch, rules_config: RulesConfig
):
    applied_offsets: list[int] = []

    def fake_apply_event(
        state: CreateGlobalStateEntity,
        event: PressEvent,
        rules_config: RulesConfig,
        rules_hash: str,
    ) -> CreateGlobalStateEntity:
        applied_offsets.append(event.offset)
        # Return new state with last_applied_offset updated to this event's offset
        return CreateGlobalStateEntity(
            last_applied_offset=event.offset,
            updated_at_ms=getattr(state, "updated_at_ms", 0),
            ruleshash=rules_hash,
            counter=getattr(state, "counter", 0) + 1,
            phase=getattr(state, "phase", 0),
            entropy=getattr(state, "entropy", 0),
            reveal_until_ms=getattr(state, "reveal_until_ms", 0),
            cooldown_ms=getattr(state, "cooldown_ms", None),
        )

    monkeypatch.setattr(updater, "apply_event", fake_apply_event)

    events = [_make_event(5, 1050), _make_event(1, 1010), _make_event(3, 1030)]
    state = _make_state()
    result = updater.apply_batch(state, events, rules_config, "hash")

    # Ensure events were processed in offset order
    assert applied_offsets == [1, 3, 5]
    # The resulting state's last_applied_offset should be the highest offset
    assert result.last_applied_offset == 5
