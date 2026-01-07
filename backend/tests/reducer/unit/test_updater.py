from shared.models import GlobalStateEntity, PressEvent, Phases
from reducer.updater import apply_event


def _state(
    updated_at_ms: int = 0, counter: int = 0, entropy: float = 0.0, phase: int = 0
):
    return GlobalStateEntity(
        id=1,
        last_applied_offset=0,
        updated_at_ms=updated_at_ms,
        ruleshash="h",
        counter=counter,
        phase=phase,
        entropy=entropy,
        reveal_until_ms=0,
        cooldown_ms=None,
    )


def _event(offset: int, ts_ms: int) -> PressEvent:
    return PressEvent(offset=offset, timestamp_ms=ts_ms, request_id=f"r{offset}")


def test_apply_event_initial_sets_dt_none_and_increments_counter(rules_config):
    state = _state(updated_at_ms=0, counter=0, entropy=0.0, phase=0)
    event = _event(10, 1000)
    new_state = apply_event(state, event, rules_config, "hash")

    # counter increments
    assert new_state.counter == 1
    # updated_at_ms set to event time
    assert new_state.updated_at_ms == 1000
    # last_applied_offset set
    assert new_state.last_applied_offset == 10
    # phase is an integer (enum value converted to int)
    assert new_state.phase in (0, 1, 2, 3)  # Phases.CALM=0, WARM=1, HOT=2, CHAOS=3
    # cooldown non-negative
    assert new_state.cooldown_ms is None or new_state.cooldown_ms >= 0


def test_apply_event_uses_positive_dt_and_progresses(rules_config):
    state = _state(updated_at_ms=1000, counter=5, entropy=0.0, phase=0)
    event = _event(11, 1100)  # 100 ms later
    new_state = apply_event(state, event, rules_config, "hash")

    assert new_state.counter == 6
    assert new_state.updated_at_ms == 1100
    assert new_state.last_applied_offset == 11
    assert new_state.entropy >= 0.0
