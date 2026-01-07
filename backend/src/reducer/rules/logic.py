from typing import Optional
from shared.models import RulesConfig, Phases


def update_entropy(
    prev_entropy: float, dt_sec: Optional[float], rules: RulesConfig
) -> float:
    """
    Update entropy based on how quickly this event arrived after the last one.
    Faster presses -> higher instantaneous intensity -> entropy drifts up.
    Slower presses / long gaps -> entropy decays toward 0.


    Args:
        prev_entropy (float): The previous GlobalState entropy
        dt_sec (Optional[float]): time in sec since the last event.
        rules (RulesConfig): ruleset applied to entropy calculations

    Returns:
        float: updated entropy value
    """
    if dt_sec is None:
        instant_intensity = 1.0
    else:
        # crude intensity: "how many presses per second would this be if repeated?"
        # clamp to avoid infinity
        instant_rate = min(1.0 / max(dt_sec, 1e-3), rules.max_rate_for_entropy)
        # normalize to [0, 1]
        instant_intensity = instant_rate / rules.max_rate_for_entropy

    alpha = rules.entropy_alpha  # e.g. 0.1
    new_entropy = (1.0 - alpha) * prev_entropy + alpha * instant_intensity

    # keep entropy between 0 and 1
    return max(0.0, min(1.0, new_entropy))


def transition_phase(entropy: float, rules: RulesConfig) -> Phases:
    """Phase is derived from entropy thresholds and is
    independent of the previous phase as the entropy can jump
    and cause jumps in phase.

    Args:
        entropy (float): current entropy value of the GlobalState
        rules (RulesConfig): ruleset to apply phase thresholds

    Returns:
        Phases: Returns the new phase
    """
    if entropy < rules.calm_threshold:
        return Phases.CALM
    elif entropy < rules.hot_threshold:
        return Phases.WARM
    elif entropy < rules.chaos_threshold:
        return Phases.HOT
    else:
        return Phases.CHAOS


def compute_cooldown_ms(
    phase: Phases,
    entropy: float,
    rules: RulesConfig,
) -> int:
    """Higher entropy / hotter phases mean longer cooldown.

    Args:
        phase (Phases): current phase
        entropy (float): current entropy value
        rules (RulesConfig): ruleset to apply phase thresholds

    Returns:
        int: new cooldown value in milliseconds
    """
    if phase == Phases.CALM:
        base = rules.cooldown_calm_ms
    elif phase == Phases.WARM:
        base = rules.cooldown_warm_ms
    else:  # CHAOS
        base = rules.cooldown_chaos_ms

    # For fun, scale a bit with entropy within the phase
    return int(base * (0.5 + 0.5 * entropy))


def compute_reveal_until_ms(
    prev_reveal_until_ms: Optional[int],
    event_ts_ms: int,
    phase: Phases,
    rules: RulesConfig,
) -> Optional[int]:
    """Decide how long the button stays "revealed"/active after this event.

    Args:
        prev_reveal_until_ms (Optional[int]): Previous reveal time
        event_ts_ms (int): timestamp of buttom press event
        phase (Phases): current phase
        rules (RulesConfig): ruleset to apply phase thresholds

    Returns:
        Optional[int]: reveal time in milliseconds
    """
    if phase == Phases.CALM:
        # maybe no reveal in CALM or very short
        duration = rules.reveal_calm_ms
    elif phase == Phases.WARM:
        duration = rules.reveal_warm_ms
    else:  # CHAOS
        duration = rules.reveal_chaos_ms

    candidate = event_ts_ms + duration
    if prev_reveal_until_ms is None:
        return candidate

    # extend the reveal window, never shorten it
    return max(prev_reveal_until_ms, candidate)
