import math
from reducer.rules.logic import (
    update_entropy,
    transition_phase,
    compute_cooldown_ms,
    compute_reveal_until_ms,
    Phases,
)


def test_update_entropy_initial_with_none_dt(rules_config):
    # When dt_sec is None (first event), intensity should be 1.0
    new_entropy = update_entropy(prev_entropy=0.0, dt_sec=None, rules=rules_config)
    assert math.isclose(new_entropy, rules_config.entropy_alpha, rel_tol=1e-6)


def test_update_entropy_clamped_high_rate(rules_config):
    # Extremely small dt -> intensity should clamp to 1.0
    prev_entropy = 0.5
    new_entropy = update_entropy(
        prev_entropy=prev_entropy, dt_sec=0.0001, rules=rules_config
    )
    expected = (
        1.0 - rules_config.entropy_alpha
    ) * prev_entropy + rules_config.entropy_alpha * 1.0
    assert math.isclose(new_entropy, expected, rel_tol=1e-6)
    assert 0.0 <= new_entropy <= 1.0


def test_transition_phase_thresholds(rules_config):
    assert (
        transition_phase(rules_config.calm_threshold - 1e-6, rules_config)
        == Phases.CALM
    )
    assert (
        transition_phase(
            (rules_config.calm_threshold + rules_config.hot_threshold) / 2.0,
            rules_config,
        )
        == Phases.WARM
    )
    assert (
        transition_phase(
            (rules_config.hot_threshold + rules_config.chaos_threshold) / 2.0,
            rules_config,
        )
        == Phases.HOT
    )
    assert (
        transition_phase(rules_config.chaos_threshold + 1e-6, rules_config)
        == Phases.CHAOS
    )


def test_compute_cooldown_ms_across_phases(rules_config):
    # Entropy scaling: base * (0.5 + 0.5 * entropy)
    assert compute_cooldown_ms(Phases.CALM, 0.0, rules_config) == int(
        rules_config.cooldown_calm_ms * 0.5
    )
    assert compute_cooldown_ms(Phases.WARM, 1.0, rules_config) == int(
        rules_config.cooldown_warm_ms * 1.0
    )
    assert compute_cooldown_ms(Phases.CHAOS, 0.5, rules_config) == int(
        rules_config.cooldown_chaos_ms * 0.75
    )


def test_compute_reveal_until_ms_extends_window(rules_config):
    now = 1_000_000
    # None previous -> set to event + duration
    assert (
        compute_reveal_until_ms(None, now, Phases.CALM, rules_config)
        == now + rules_config.reveal_calm_ms
    )
    # Extends and never shortens
    prev = now + 1000
    candidate = now + rules_config.reveal_chaos_ms
    result = compute_reveal_until_ms(prev, now, Phases.CHAOS, rules_config)
    assert result == max(prev, candidate)
