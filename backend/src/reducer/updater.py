from shared.models import (
    GlobalStateEntity,
    RulesConfig,
    PressEvent,
    CreateGlobalStateEntity,
)
from reducer.rules import logic as rules_logic
from typing import List


def apply_event(
    state: GlobalStateEntity,
    event: PressEvent,
    rules_config: RulesConfig,
    rules_hash: str,
) -> CreateGlobalStateEntity:

    if state.updated_at_ms == 0:
        dt_sec = None
    else:
        # Raw delta in milliseconds
        dt_ms = event.timestamp_ms - state.updated_at_ms

        # Avoid divide-by-zero or negative values (clock drift or out-of-order msg)
        dt_ms = max(dt_ms, 1)  # at least 1 ms
        dt_sec = dt_ms / 1000.0  # convert to seconds

    new_state_counter = state.counter + 1

    new_entropy = rules_logic.update_entropy(state.entropy, dt_sec, rules_config)
    new_phase = rules_logic.transition_phase(new_entropy, rules_config)
    new_countdown = rules_logic.compute_cooldown_ms(
        new_phase, new_entropy, rules_config
    )
    new_reveal = rules_logic.compute_reveal_until_ms(
        state.reveal_until_ms, event.timestamp_ms, new_phase, rules_config
    )

    return CreateGlobalStateEntity(
        last_applied_offset=event.offset,
        updated_at_ms=event.timestamp_ms,
        ruleshash=rules_hash,
        counter=new_state_counter,
        phase=new_phase.value,  # Convert Phases enum to int
        entropy=new_entropy,
        reveal_until_ms=new_reveal,
        cooldown_ms=new_countdown,
    )


def apply_batch(
    state: GlobalStateEntity,
    events: List[PressEvent],
    rules_config: RulesConfig,
    rules_hash: str,
) -> CreateGlobalStateEntity:
    new_state = state
    for event in sorted(events, key=lambda e: e.offset):
        new_state = apply_event(new_state, event, rules_config, rules_hash)

    return new_state
